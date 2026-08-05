# Development Log

## 2026-07-30

### Summary
Defined the project scope and got the local development environment
ready for the OCR pipeline.

### What Was Done
- Wrote `README.md` with the project overview, goals, tech stack, and
  MVP scope
- Wrote `docs/architecture.md` describing the OCR -> LLM parsing ->
  SQLite -> query agent system flow
- Wrote `docs/decisions.md`, documenting key technical decisions
  (OCR engine, storage, agent framework, build sequencing) with
  options considered and tradeoffs
- Wrote `docs/roadmap.md` with the phased build order
- Configured `.gitignore` for Python (`.venv/`, `__pycache__/`,
  `.env`, `*.db`/`*.sqlite3`, `.DS_Store`)
- Installed the Tesseract OCR engine via Homebrew (`tesseract 5.5.3`)
- Created a project virtual environment (`.venv`) — noted that
  installing Tesseract's dependency chain via Homebrew silently
  bumped the global `python3` from 3.13.7 to 3.14.6; not an issue
  since the venv is self-consistent, but worth remembering as a
  general Homebrew gotcha
- Installed `pytesseract` and `Pillow` into the venv
- Smoke-tested the install by calling `pytesseract.get_tesseract_version()`
  end-to-end (Python -> pytesseract -> subprocess -> Tesseract binary
  -> back to Python) to confirm the toolchain is wired up correctly
  before writing any real OCR logic against it

### Next Steps
- Step 1: get a real receipt image into the project and run the
  first actual OCR pass with pytesseract, then inspect the raw text
  output for quality/noise before designing the LLM parsing step

---

## 2026-07-31

### Summary
Got a real receipt photo into the project and built out `src/ocr.py`
with a working OCR preprocessing pipeline, completing Step 1 of the
roadmap.

### What Was Done
- Added a real receipt photo (`data/receipts/receipt-01.jpg`),
  converted from HEIC to JPEG via macOS `sips`
- Built `src/ocr.py` with an `extract_text()` function, iterated
  through several rounds of preprocessing based on real OCR output

### Issues & Resolutions
- **Rotation:** raw OCR on the unprocessed photo produced total
  garbage. Diagnosed by visually inspecting the image (not guessed):
  the photo was physically sideways. Fixed with a manual 90-degree
  rotation.
- **OSD unreliable:** tried Tesseract's automatic orientation
  detection (OSD) instead of a hardcoded rotation, but it failed/gave
  low-confidence wrong answers on this photo — the receipt only fills
  part of the frame, and the wood-grain clipboard background was
  enough noise to defeat it. Fell back to the fixed manual rotation.
- **Missing item table:** after fixing rotation, the item/qty/price
  table was still dropped entirely. Diagnosed as a page-segmentation
  issue — Tesseract's default mode assumes paragraph text, not a
  columnar table. Tested several `--psm` modes; `--psm 6` (uniform
  block of text) was the only one that recovered table content.
- **Remaining noise:** text was still noisy throughout. Added
  grayscale + adaptive thresholding (binarizing to clean black/white,
  computed locally so uneven lighting doesn't get misread) using
  OpenCV. A light Gaussian blur was added before thresholding to
  smooth fine background noise that would otherwise survive as
  speckle and get misread as text. Blur kernel size was tuned
  empirically (3x3 vs 5x5) against real OCR output — 5x5 removed more
  noise but also eroded real character strokes and lost item rows, so
  3x3 was chosen as the better balance.

### Future Considerations
- Rotation angle, blur kernel size, and adaptive threshold params
  were all tuned against a single real receipt (one lighting
  condition, one camera, one paper type) — not guaranteed to
  generalize. Revisit once Step 4 (batch processing) provides a
  representative sample of real receipts to validate against, rather
  than auto-tuning now off a sample size of one.
- Cropping the receipt out of the background before OCR would likely
  improve both OSD reliability and general OCR quality, but requires
  real boundary-detection logic — bigger scope than Step 1, revisit
  later if noise remains a problem at batch scale.

### Next Steps
- Step 2: prompt-engineer an LLM call that parses this raw OCR text
  into structured JSON (merchant, date, line items, totals)

---

## 2026-08-02

### Summary
Built `src/parse.py`, an LLM parsing step that turns Step 1's raw OCR
text into structured JSON, using Claude tool use for guaranteed
schema-shaped output.

### What Was Done
- Set up an Anthropic API key in `.env` (already gitignored from day
  one for this purpose) and installed `anthropic` + `python-dotenv`
- Built `src/parse.py`: defines a `record_receipt` tool schema
  (merchant, date, line_items, subtotal, tax, total) and forces
  Claude to respond via that tool (`tool_choice`) instead of parsing
  free-form text out of a response
- Moved standing instructions into a `system` prompt, separate from
  the per-call OCR text in the user message, for a cleaner
  separation between fixed behavior and variable input

### Issues & Resolutions
- **Merchant/date came back missing, some items had wrong/missing
  data:** compared the parsed output against the actual raw OCR text
  and confirmed most of this was correct behavior, not a parsing bug
  — the info genuinely isn't present in the OCR text (see Step 1's
  known noise). Real, fixable issues found this way: OCR noise words
  leaking into item names (e.g. `"Joe of Maker's Mark"`), and the
  model defaulting a missing quantity to `1` instead of leaving it
  out. Both addressed via explicit system prompt instructions.
- **`temperature` param rejected:** attempted to set `temperature=0`
  for more consistent extraction, but this specific model
  (`claude-sonnet-5`) has deprecated that parameter. Removed it.
- **Inconsistent missing-value representation:** across runs, missing
  prices showed up sometimes as `null`, sometimes omitted, and in one
  run as `0` (misleading — implies "free," not "unknown"). Likely
  normal response variance we can no longer damp with `temperature`.
  Not yet fixed.

### Future Considerations
- Before tightening the parsing prompt further (e.g. explicitly
  banning `0` as a stand-in for unknown), clean up OCR quality more
  first — several of today's "errors" traced back to OCR data loss,
  not the LLM. Better input may shrink how much defensive prompting
  the parsing step even needs. Revisit prompt tightening after that.
- The arithmetic cross-check idea from Step 1/2 discussions (does
  sum of line items ~= subtotal, does subtotal + tax ~= total) is
  still a good, cheap way to flag likely-wrong extractions
  regardless of cause — not built yet, still a good candidate for a
  future validation pass.

### Next Steps
- Improve OCR quality further, then revisit LLM parsing prompt
  tightening with cleaner input to test against

---

## 2026-08-03

### Summary
Improved OCR by cropping background out of the photo, evidence-tested
several other preprocessing ideas, and tightened the parsing prompt
based on what those tests revealed.

### What We Tried

- **Cropping background out (`crop_to_receipt`) — kept.** Original
  plan was a closed 4-point contour + perspective warp (like a mobile
  scanner app), but the photo's bottom edge runs off-frame, so a
  closed contour could never form there. Switched to a bounding box
  around all significant detected edges instead — falls back to the
  image's own boundary when content runs off-frame, no special case
  needed. Recovered real data we never had before (merchant name,
  correct surcharge amount).
- **Less/no blur — tried, not kept.** Recovered a bit more text, but
  introduced confidently wrong numbers (e.g. a clean-looking but
  incorrect `$14,000`) instead of obviously garbled ones. A wrong
  answer that looks right is worse than one that looks uncertain, so
  we kept the existing blur.
- **Deskewing residual tilt — tried, not kept.** Verified the
  correction direction visually before trusting it (same as our
  original rotation fix), and it did straighten the image and
  recover a previously-missing item in the raw OCR text. But checking
  the full parsed JSON (not just raw text) showed a hallucination
  ("Coca-Cola" instead of "Diet Cola") and a split/malformed item.
  Raw text looked better; the real output got worse.
- **CLAHE contrast enhancement — tried, not kept.** Expected to help
  faint print stand out. Instead massively amplified fine noise —
  the worst result of any test today, by a wide margin. Ruled out
  without further tuning.
- **Tesseract user-words (custom vocabulary) — tried, no effect.**
  Loaded correctly but changed nothing. Makes sense in hindsight: it
  only helps disambiguate near-miss word spelling, and our remaining
  failures are mostly numeric or too garbled to be "near" any real
  word.
- **Parsing prompt tightening — kept.** Found two real issues by
  comparing parsed JSON against raw OCR text: the model sometimes
  substituted an unrelated labeled value into a field it couldn't
  find (e.g. surcharge amount used as tax), and sometimes used
  placeholder values (`0`, `"UNKNOWN"`) instead of omitting a field.
  Both fixed via explicit system prompt instructions.

### Future Considerations
- Several tests today only revealed real regressions when checking
  the *full parsed JSON*, not raw OCR text alone (deskew looked like
  a win in raw text, was a net loss end-to-end). Keep evaluating
  changes against full pipeline output going forward.
- Likely near the ceiling of what preprocessing alone can do on this
  one photo. Further real improvement probably needs a batch of
  receipts to validate against (see Step 4), better source photos, or
  a fundamentally different OCR approach (cloud OCR / vision-LLM,
  already flagged in docs/decisions.md as the scale-up path).
- `MIN_CONTOUR_AREA_RATIO` (0.001) is still an untested default

### Next Steps
- Step 3: persist parsed receipt JSON into SQLite via SQLAlchemy

---

## 2026-08-05

### Summary
Built Step 3 (SQLite storage), then added two more real receipt
photos and used them to pressure-test Step 1's pipeline -- several
things tuned against one photo turned out not to generalize, exactly
as flagged as a risk back on 2026-07-31.

### What Was Done
- Installed SQLAlchemy. Built `src/storage.py`: `Receipt` and
  `LineItem` ORM models (one-to-many via foreign key), `init_db()`,
  and `save_receipt()` to persist parse.py's output.
- `date` is stored as a real `Date` column (not a plain string) so
  future date-range queries (Step 5) are possible, with a
  `date_is_estimated` boolean alongside it -- when parse.py can't
  extract a date, we fall back to today's date rather than leaving it
  null, but flag it so a fallback date is never silently treated as
  reliable as a real one.
- Updated parse.py's schema to request dates in `YYYY-MM-DD` format
  directly from Claude, instead of writing our own date-parsing logic
  for whatever loose format the OCR text happened to contain.
- Tested the full OCR -> parse -> store -> query pipeline
  end-to-end successfully.
- Added `receipt-02.jpg` and `receipt-03.jpg` (converted from HEIC,
  same naming convention as receipt-01).

### Issues & Resolutions
- **Fixed rotation assumption failed:** `receipt-02`/`03` came in
  already upright, unlike `receipt-01`. The hardcoded `-90` rotation
  would have wrongly rotated correct photos. Replaced with a
  geometric heuristic: crop first, then rotate only if the crop is
  wider than tall (a correctly-oriented receipt is always a tall
  strip). Re-tested Tesseract's OSD after cropping too, hoping
  cropping would fix its earlier unreliability -- it didn't
  (low-confidence wrong answer on receipt-01, low-confidence
  coincidentally-right answer on receipt-03, no usable way to trust
  either). Kept the simpler geometric heuristic instead.
- **Crop threshold failed on a low-contrast background:**
  `crop_to_receipt()` found zero significant contours on `receipt-02`
  (light tablecloth background) and threw our own validation error.
  Diagnosed via the raw edge map: text was detected fine, but there
  was no single large boundary contour the way `receipt-01`'s dark
  wood background produced, and no individual text-line contour was
  big enough alone to pass the old threshold. Lowered
  `MIN_CONTOUR_AREA_RATIO` (0.001 -> 0.00025), verified against both
  photos this doesn't reintroduce background noise into receipt-01's
  crop. Not perfect: receipt-02's crop still clips slightly at one
  edge.
- **`--psm 6` doesn't generalize either -- found, not fixed.**
  `receipt-03` (Walgreens, different layout/fonts than receipt-01)
  preprocessed into a genuinely clean, readable image, but `--psm 6`
  dropped the entire header/total and only recovered footer text.
  Tested psm 3/4/11 too -- none handled the whole receipt well.
  Left unresolved for now rather than chasing a fourth per-image
  tuning fix in one session.

### Future Considerations
- Real pattern across today: several things tuned against one photo
  (rotation direction, crop threshold, PSM mode) didn't hold up
  against different real photos. Confirms the plan from 2026-07-31 --
  validate against a representative sample, not a sample of one.
- Decided not to keep chasing the PSM issue for perfect automated
  accuracy. Instead: build toward a lightweight review/correction UI
  later (a real, deliberate strategy, not a fallback) -- accept good-
  but-imperfect automated extraction and let a human quickly fix
  what's wrong, rather than trying to perfect OCR against every
  possible receipt layout. Only works if automation stays "mostly
  right, specific known gaps" rather than "mostly wrong" -- true
  today, worth re-checking if it stops being true.

### Next Steps
- Step 4: loop the full pipeline over the receipts folder
- Longer term: a lightweight Streamlit UI for uploading + reviewing/
  correcting parsed receipts (already anticipated in README's
  original scope)
