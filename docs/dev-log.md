# Development Log

## 2026-07-30

Defined the project scope and got the dev environment set up for the
OCR pipeline. Wrote README.md, docs/architecture.md, docs/decisions.md,
docs/roadmap.md. Configured .gitignore for Python (.venv/, __pycache__/,
.env, *.db/*.sqlite3, .DS_Store).

Installed Tesseract via Homebrew (5.5.3). Installing its dependency
chain silently bumped global python3 from 3.13.7 to 3.14.6 -- not a
problem since the venv is self-consistent, but a good reminder that
Homebrew can do that. Created the venv, installed pytesseract +
Pillow, smoke-tested with `pytesseract.get_tesseract_version()`
end-to-end before writing any real OCR logic.

Next: get a real receipt photo in and run the first actual OCR pass,
inspect the raw text quality before designing the parsing step.

---

## 2026-07-31

Got a real receipt photo in (receipt-01.jpg, converted from HEIC via
sips) and built src/ocr.py. Took a few rounds to get right.

Raw OCR on the unprocessed photo was total garbage. Looked at the
image directly instead of guessing -- it was physically sideways.
Fixed with a manual 90-degree rotation. Tried Tesseract's OSD
(automatic orientation detection) instead of hardcoding the angle,
but it gave low-confidence wrong answers -- the receipt only fills
part of the frame and the wood-grain clipboard background was enough
noise to throw it off. Went back to the fixed rotation.

After fixing rotation, the item/price table still wasn't showing up
at all. Turned out to be a page-segmentation issue -- Tesseract's
default mode assumes normal paragraph text, not a column layout.
`--psm 6` (treat it as one uniform block) was the only mode that
recovered the table.

Text was still noisy after that. Added grayscale + adaptive
thresholding (local, not global, so uneven lighting doesn't get
misread as text) plus a light blur beforehand to smooth background
noise without eroding character strokes. Tested 3x3 vs 5x5 blur --
5x5 killed more noise but also ate real character strokes and lost
item rows, so went with 3x3.

Worth remembering: rotation angle, blur size, threshold params were
all tuned against exactly one photo (one lighting setup, one camera,
one paper type) -- no guarantee this generalizes. Revisit once I've
got a batch of receipts to check against. Cropping the receipt out of
the background before OCR would probably help both OSD and general
quality, but that's real boundary-detection work, bigger than Step 1
-- later if noise is still a problem at batch scale.

Next: Step 2, prompt-engineer an LLM call that turns this raw OCR
text into structured JSON.

---

## 2026-08-02

Built src/parse.py -- takes Step 1's raw OCR text and turns it into
structured JSON via Claude tool use, so the output shape is
guaranteed instead of parsing free text myself.

Set up an Anthropic API key in .env (already gitignored from day one
for exactly this). Installed anthropic + python-dotenv. Defined a
record_receipt tool schema and forced Claude to respond through it.
Split instructions into a system prompt, separate from the actual
per-call OCR text -- keeps fixed behavior and variable input apart.

Merchant/date came back missing on the first runs, some items had
wrong or missing data. Checked the parsed output against the raw OCR
text and most of it turned out to be correct behavior -- the info
genuinely isn't in the text, matches Step 1's known noise. Two real
bugs found this way though: OCR noise words leaking into item names
("Joe of Maker's Mark"), and the model defaulting a missing quantity
to 1 instead of leaving it out. Fixed both with explicit prompt
instructions.

Tried setting temperature=0 for more consistent output -- turns out
this model has that param deprecated. Dropped it.

Missing prices are showing up inconsistently -- sometimes null,
sometimes just omitted, once as 0 (bad, implies "free" not
"unknown"). Probably normal response variance I can't damp with
temperature anymore. Not fixed yet.

Idea for later: an arithmetic cross-check (does sum of line items ~=
subtotal, subtotal + tax ~= total) would be a cheap way to flag
likely-wrong extractions regardless of cause. Haven't built it.

Next: clean up OCR more first, then come back and tighten the parsing
prompt against cleaner input.

---

## 2026-08-03

Cropped the background out of the photo, tested a handful of other
preprocessing ideas, tightened the parsing prompt based on what the
tests showed.

**Cropping (kept).** Original plan was a closed 4-point contour +
perspective warp, like a phone scanner app. Didn't work -- the
photo's bottom edge runs off-frame, so a closed contour never forms
there. Switched to a bounding box around every significant detected
edge instead, which naturally falls back to the image's own boundary
when content runs off-frame. Recovered real data I never had before
(merchant name, a correct surcharge amount).

**Less/no blur (tried, didn't keep).** Got a bit more text back, but
also introduced confidently wrong numbers -- a clean-looking but
wrong $14,000 instead of an obviously garbled one. A wrong answer
that looks right is worse than one that looks uncertain, so kept the
blur as-is.

**Deskew (tried, didn't keep).** Checked the correction direction
visually before trusting it, same as the rotation fix. Straightened
the image fine and pulled in a previously-missing item in the raw
text. But the actual parsed JSON got worse -- a hallucinated
"Coca-Cola" instead of "Diet Cola," a split/malformed item. Raw text
looked better, real output didn't.

**CLAHE contrast (tried, didn't keep).** Wanted to help faint print
stand out. Instead massively amplified noise -- worst result of the
day by a wide margin. Ruled out without bothering to tune it further.

**Tesseract user-words / custom vocabulary (tried, no effect.)**
Loaded fine, changed nothing. Makes sense in hindsight -- it only
helps with near-miss word spelling, and what's still failing is
mostly numeric or too garbled to be "near" any real word.

**Parsing prompt tightening (kept).** Compared parsed JSON against
raw OCR text and found two real bugs: the model sometimes swapped in
an unrelated labeled value when the field it wanted wasn't there
(surcharge used as tax), and sometimes used placeholder values (0,
"UNKNOWN") instead of just omitting the field. Fixed both with
explicit prompt instructions.

Takeaway: a few of today's "wins" only looked like wins in raw OCR
text and turned out worse once I checked the actual parsed JSON.
Need to keep checking full pipeline output, not just the OCR step in
isolation. Also: probably near the ceiling of what preprocessing
alone can do on this one photo -- next real improvement needs a
batch of receipts to validate against, better source photos, or a
different OCR approach entirely (cloud OCR / vision-LLM, already
flagged in decisions.md as the scale-up path).
MIN_CONTOUR_AREA_RATIO (0.001) is still an untested default.

Next: Step 3, persist parsed JSON into SQLite via SQLAlchemy.

---

## 2026-08-05

Built Step 3 (SQLite storage), then added two more real receipt
photos and used them to pressure-test Step 1 -- exactly the
generalization risk flagged back on 7/31, now with real evidence.

Installed SQLAlchemy. Built src/storage.py: Receipt and LineItem
models (one-to-many via foreign key), init_db(), save_receipt(). date
is a real Date column, not a string, so date-range queries are
possible later, plus a date_is_estimated flag -- when parse.py can't
find a date I fall back to today's date, but flag it so a fallback
never gets silently treated as trustworthy as a real one. Updated
parse.py to ask Claude for dates in YYYY-MM-DD directly rather than
writing my own date-parsing logic. Full OCR -> parse -> store -> query
pipeline tested end-to-end. Added receipt-02.jpg and receipt-03.jpg.

Rotation assumption broke immediately -- receipt-02/03 came in
already upright, unlike receipt-01. The hardcoded -90 would've wrongly
rotated correct photos. Replaced with a geometric rule instead: crop
first, then only rotate if the crop comes out wider than tall (a
right-side-up receipt is always a tall strip). Gave Tesseract's OSD
another shot after cropping, hoping cropping would fix its earlier
unreliability -- nope. Wrong answer, low confidence on receipt-01;
right answer, still low confidence on receipt-03. No way to trust
either outcome, so kept the simple geometric rule.

Crop also broke outright on receipt-02's low-contrast background --
zero significant contours found, hit my own validation error. Checked
the raw edge map: text detected fine, but no single big boundary
contour the way receipt-01's dark wood background gave me, and no
individual text-line contour big enough alone to pass the threshold.
Lowered MIN_CONTOUR_AREA_RATIO (0.001 -> 0.00025), checked it doesn't
let background noise back into receipt-01's crop. Still not perfect
-- receipt-02's crop clips slightly on one edge.

--psm 6 doesn't generalize either. receipt-03 (Walgreens, different
layout/fonts) preprocessed into a genuinely clean image, but --psm 6
dropped the whole header/total and only recovered the footer. Tried
psm 3/4/11 too, none handled the whole receipt. Left it unresolved
rather than chase a fourth tuning fix in one sitting.

Real pattern today: several things tuned against one photo (rotation
direction, crop threshold, PSM mode) didn't hold up against different
real photos -- exactly why the plan was to validate against a real
sample instead of one image. Also decided to stop chasing the PSM
issue for perfect accuracy and instead build toward a lightweight
correction UI later -- accept good-but-imperfect automation and fix
what's wrong by hand, rather than trying to perfect OCR for every
possible layout. Only works as long as automation stays "mostly
right, known gaps" instead of "mostly wrong" -- worth rechecking if
that stops being true.

Next: Step 4, loop the pipeline over the receipts folder. Longer
term: a lightweight Streamlit UI for uploading/reviewing/correcting
receipts (already in README's original scope).

---

## 2026-08-08

Poked at the --psm 6 gap from last time (inconclusive, dropped it),
then built Step 4: batch processing with real dedup, which turned up
and fixed a real schema bug.

Tested two theories for why --psm 6 drops receipt-03's header (OCR'd
in isolation, OCR'd with the logo cropped out). Both inconclusive --
excluding the logo actually made results worse, which kills the "logo
confuses segmentation" theory. Left it as a known, unresolved
limitation instead of continuing to chase it -- matches the decision
from last session to lean on a correction UI instead of perfecting
every OCR edge case.

Built src/batch.py -- loops OCR -> parse -> store over data/receipts/,
catches per-receipt failures so one bad photo doesn't kill the whole
batch. Added real dedup to storage.py: a content_hash (SHA-256 of the
image bytes) instead of filename, so a renamed or re-uploaded
duplicate still gets caught later, e.g. once there's an upload UI
where filenames can't be trusted. Checked before running OCR/LLM so a
duplicate doesn't cost an API call. Wrote up the deferred file-storage
decision (local disk now, S3 once there's a real UI) in decisions.md.

Batch run crashed on receipt-02 -- Claude returned the literal string
"<UNKNOWN>" for total, a required numeric field, and it crashed trying
to save a string into a numeric column. Wasn't really inconsistent
model behavior -- it was a real contradiction in my own schema. total
was required (key has to be present) while the prompt said never
guess or use a placeholder for something unknown. When the true total
genuinely wasn't in the text (receipt-02's OCR was badly degraded),
there was no way to satisfy both rules at once. Fixed by letting
total's value be null ("type": ["number", "null"]) -- required key,
honestly nullable value -- and making the DB column nullable to
match.

Same bug showed up in merchant on the next run, just didn't crash
this time (a string fits a string column fine) -- returned "UNKNOWN"
instead. Confirms it's a general pattern: any required field where
the model might genuinely not know the answer needs the same fix.
line_items doesn't have this problem -- an empty array already means
"found nothing" honestly. Applied the same fix to merchant.

Worth remembering for any new required fields added later --
required-but-possibly-unknowable fields need null explicitly allowed,
not just a "don't guess" instruction.

Next: Step 5, LangChain query agent over stored receipts.

---

## 2026-08-13

Built Step 5 -- the LangChain query agent. Roadmap's core pipeline is
now complete end-to-end: photo in, natural-language answer out.

Added a category field (fixed list, not free text, so values stay
consistent enough to actually query later) to parse.py's schema and
storage.py's Receipt model -- needed this for the roadmap's own
example question ("how much did I spend on food"). Left it null when
genuinely unclear, same rule as everything else. Reprocessed all 3
receipts via batch.py to backfill it.

Installed langchain, langchain-anthropic, langgraph -- first
LangChain code in the project; Step 2 deliberately used the raw
Anthropic SDK instead, per the original tech split. Built
src/agent.py: two hand-built tools (sum_spending(), lookup_receipts(),
both filterable by merchant/category/date) instead of LangChain's SQL
Agent Toolkit. Wanted to keep the small action space from README's
own design, and wanted to write the actual SQL myself rather than
trust the LLM to generate correct queries live -- same "don't trust
ungrounded LLM output" rule I've been holding to everywhere else in
this project.

Used langchain.agents.create_agent (the current API) instead of
langgraph.prebuilt.create_react_agent -- same call, but it's flagged
deprecated at import time. Checked the installed package's actual
signature instead of copying older tutorial code. System prompt
carries today's real date (computed fresh, not hardcoded) so the
agent can resolve stuff like "this month" into real date ranges, plus
the category list, plus an instruction to ask for clarification
instead of guessing.

On a more complex question, the agent's raw response dumped a giant
base64 "thinking" block straight into the output instead of clean
text. Same underlying thing as parse.py's tool_use handling from Step
2 -- message content isn't always a plain string, can be a list of
typed blocks (thinking + text). Fixed ask() to pull out just the text
blocks.

Remaining ideas, not formal roadmap steps: a correction UI
(Streamlit), revisiting the --psm 6 gap with more real photos, cloud
OCR/S3 if this ever needs to scale past personal use.

---

## 2026-08-13 (part 2)

Built app.py -- a Streamlit UI over the whole pipeline: upload,
review/correct, browse, chat.

Mapped out what a real production version would need first --
multi-tenant auth with non-negotiable user-scoped queries, S3, managed
OCR, Postgres, async job processing + state tracking, migrations,
tests, observability, secrets management. Good to know, but way more
operational surface than a tool with one user needs. Streamlit reuses
the pipeline exactly as-is, no API layer, gets to something usable
today instead of mid-build. Also decided not to host this publicly
open to anyone, at least not yet -- public + unauthenticated +
LLM-backed means anyone with the link can burn through real API
budget with no ceiling, and I'd want a hard usage cap in place before
ever doing that. Nothing deployed right now. SQLite/local files stay
as they are too -- only reason to swap to hosted Postgres/S3 would be
needing durable storage on free hosting (Streamlit Community Cloud's
free tier doesn't reliably keep local disk across restarts), and
that's not a problem I have yet.

Installed streamlit. app.py lives at the repo root and imports src/
modules directly -- single Python process, no API needed. Upload page:
file uploader -> hash-check against receipt_exists() before running
OCR/LLM (same dedup as batch.py) -> extract + parse, cached in
st.session_state keyed by content hash so Streamlit's rerun-the-whole-
script-on-every-interaction model doesn't redo OCR/LLM on every
keystroke -> editable review form -> save. Review form uses text
inputs, not number inputs, for optional numeric fields, converting
blank to None on save -- number_input can't represent "unknown," only
a numeric default like 0.0, which would quietly turn "don't know the
tax" into "tax is $0" and undo the honest-nulls thing I've been
careful about since Step 2. Browse page is just a table of everything
stored. Ask page is a chat interface wrapping agent.py's ask().

Actually ran the app instead of just reading the code -- Streamlit
locally plus a Playwright driver script, since chromium-cli wasn't
available in this environment. Cleaned up the test data afterward so
nothing fake ended up mixed in with my real receipts.

Next: record a short demo video/GIF for the README.
