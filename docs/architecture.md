# Architecture

## System Flow

Receipt image
  -> OCR (Tesseract via pytesseract)
  -> Raw text
  -> LLM parsing (structured JSON extraction)
  -> SQLite storage (SQLAlchemy ORM)
  -> Natural-language query agent
  -> Answer (SQL aggregation, lookup, or clarification)

## Components

### OCR Layer
Reads a receipt image and produces raw text. Tesseract quality on real
receipts is the biggest unknown, which is why it's built and inspected
first, before any parsing logic is designed against it.

### Parsing Layer
An LLM call that takes raw OCR text and returns structured JSON
(merchant, date, line items, totals, etc). Prompt-engineered rather
than rule-based, since OCR output is noisy and inconsistent.

### Storage Layer
SQLite via SQLAlchemy ORM. Chosen for zero-setup local development
with a clear upgrade path to Postgres later without changing the data
access code.

### Query Agent
Takes a natural-language question and decides what action to take:
run a SQL aggregation, look up a single record, or ask the user for
clarification. This decision-making step is the core "agentic"
behavior being practiced in this project — the agent reasons over a
small, fixed action space rather than following hardcoded branching
logic.

## Future Scaling Considerations (not built now, but can be articulated)
- Decouple upload from processing via a queue (Redis/SQS)
- Parallelize OCR, rate-limit LLM calls
- Swap SQLite -> Postgres for concurrent writes
- Add job-state tracking (pending/ocr_done/parsed/stored/failed) for
  retryability and observability
- Add monitoring on queue depth, latency, failure rate per stage