# Roadmap

This roadmap outlines the phased build order for the Personal Receipt/
Expense Agent. Sequencing is deliberate: build against the messiest
real input first (OCR quality is the biggest unknown), rather than
designing against imagined clean data.

---

## Step 1: OCR on One Real Receipt

### Goal
Get Tesseract extracting text from a single real receipt image and
inspect the raw output.

### Outcome
A clear picture of OCR quality/noise to design the parsing step
against.

---

## Step 2: LLM Parsing

### Goal
Prompt-engineer an LLM call that takes the raw OCR text from Step 1
and returns structured JSON (merchant, date, line items, totals).

### Outcome
A structured record from a single receipt.

---

## Step 3: SQLite Storage

### Goal
Persist the structured JSON record using SQLAlchemy ORM into SQLite.

### Outcome
A queryable local database with at least one stored receipt.

---

## Step 4: Batch Processing

### Goal
Loop the OCR -> parse -> store pipeline over a folder of multiple
receipt images.

### Outcome
A small dataset of real, stored receipts to query against.

---

## Step 5: Natural-Language Query Agent

### Goal
Build a LangChain agent that takes a natural-language question (e.g.
"how much did I spend on food this month?") and decides which action
to take: SQL aggregation, single lookup, or asking for clarification.

### Outcome
A working end-to-end demo: receipt image in, natural-language answer
out. This is the core "agentic" deliverable of the project.

---

## Guiding Principles
- Build against real, messy input before designing for clean data
- Validate each stage before building the next on top of it
- Keep scope to a single-user, single-image-at-a-time MVP; defer
  RAG, multi-agent, and proactive/scheduled behavior to a future
  project
