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
