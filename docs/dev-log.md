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
