# Engineering Decisions

This document tracks key technical decisions made during development
of the Receipt/Expense Agent. Each decision includes options
considered, reasoning, and tradeoffs.

---

## 1. OCR Engine Selection

### Options Considered
- Tesseract (via pytesseract)
- Cloud OCR APIs (Google Vision, AWS Textract)

### Chosen
Tesseract via pytesseract

### Reasoning
Free, local, no API keys or cost while learning. Good enough to
surface real OCR quality issues on receipts, which is the point of
starting here first.

### Tradeoffs
Lower accuracy than cloud OCR on low-quality images (crumpled
receipts, poor lighting). Acceptable for a portfolio/learning project
working with a small number of real images.

---

## 2. Storage Selection

### Options Considered
- SQLite
- Postgres

### Chosen
SQLite, via SQLAlchemy ORM

### Reasoning
Zero-setup local development. Using SQLAlchemy ORM instead of raw
sqlite3 keeps a clean path to swap in Postgres later without
rewriting data access code, if this evolves past a single-user
portfolio project.

### Tradeoffs
Not suitable for concurrent writes at scale — acceptable for MVP.

---

## 3. Agent Framework Selection

### Options Considered
- LangChain
- Raw LLM API calls with hand-rolled tool-use loop

### Chosen
LangChain

### Reasoning
Primary goal is to learn LangChain fundamentals as part of the
transition into agentic AI work, not just to solve the task in the
fewest lines of code.

### Tradeoffs
More framework overhead/abstraction to learn upfront compared to a
hand-rolled loop, but that's the explicit learning goal here.

---

## 4. Project Scope Strategy

### Options Considered
- Build full pipeline (OCR + parsing + storage + query agent) before
  testing any one piece
- Build and validate one stage at a time, starting with the messiest
  input (OCR)

### Chosen
Build and validate one stage at a time, OCR first

### Reasoning
OCR quality on a real receipt is the biggest unknown. Building
against real, messy OCR output from the start avoids designing
parsing/storage logic against imagined clean data.

### Tradeoffs
Slower to reach an end-to-end demo, but each stage is validated
against real data before the next is built on top of it.

---

## 5. Receipt File Storage (local disk now, S3 later)

### Options Considered
- Local filesystem (`data/receipts/`)
- Cloud object storage (e.g. AWS S3)

### Chosen
Local filesystem for now

### Reasoning
There's no UI yet -- receipts are added manually by the developer.
Local files are simplest and require no cloud credentials or cost
for a single-user CLI tool at this stage.

### Tradeoffs
Won't work once there's a real upload UI: a database shouldn't store
large binary image data directly, and a future UI needs files to live
somewhere addressable independent of any one machine. S3 is the clear
next step then -- it also pairs naturally with cloud OCR (e.g. AWS
Textract can read directly from S3), so the two deferred decisions
(cloud OCR, cloud file storage) would likely land together. Deferred
until there's an actual UI that needs it, consistent with the rest of
this project's MVP scope.
