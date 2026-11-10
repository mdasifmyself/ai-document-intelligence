# Testing

Three layers of testing, each run many times during development:

1. **Automated test suite** (pytest): 90 tests against a real PostgreSQL + pgvector, real Redis and real Tesseract
   OCR. Runs in GitHub Actions on every push, and inside the production server before each deployment.
2. **Measured evaluation (backtesting)** on a labelled dataset of 96 files and a 1,000-page batch, run against the
   live system from a clean state after every important change. See [08-evaluation-report.md](08-evaluation-report.md).
3. **Manual end-to-end checks** in the browser on the deployed demo: every page, desktop and phone width, error
   states, upload of every file type, correction and approval, export.

## Run the tests

```bash
docker compose up -d db redis
cd backend
pip install -r requirements-dev.txt          # Tesseract must be installed (apt install tesseract-ocr)
TEST_DATABASE_URL=postgresql+psycopg://docintel:docintel@localhost:5432/docintel_test \
REDIS_URL=redis://localhost:6379/15 pytest -rf --cov=app
```

The tests use a separate database (`docintel_test`, created automatically), run background jobs inline, and use a
deterministic fake AI (no network, no cost). The fake AI reads the simple test layout with regular expressions and
can be switched to "outage" or to "lies" (inventing values) to test those paths.

## What is covered

| File | Tests | Covers |
|---|---|---|
| `test_units.py` | 26 functions (50 cases) | File-type detection from content (incl. renamed, empty, cut, unsupported files); amount parsing (`1.234,50`, `(45.00)`, South Asian grouping); date parsing and ambiguity; name and number normalisation; the evidence guard (exact, OCR-fuzzy, invented quote, value not in quote); every validation rule (total, rounding tolerance, line maths, missing, negative, future date, tax rate, unverified, spreadsheet rows); invoice splitting in batch PDFs; dual-reading reconciliation (agreement, arithmetic settles amounts, misread line fixed from image, unresolved disagreement flagged, empty or amount-less line items never win) |
| `test_readers.py` | 10 | Digital PDF text layer; scanned PDF → OCR with confidence; sideways photo rotated by OCR orientation detection; noisy JPEG and multi-page TIFF; password-protected PDF; truncated image read with a warning; header synonym matching; XLSX with invoices + line items + extra sheet (cell evidence such as `Invoices!G2`); legacy XLS; EU-style CSV; corrupted spreadsheet |
| `test_api.py` | 13 | Access code required; upload → background job → result with evidence for a digital PDF (every stage in the history); scanned PDF, noisy photo, XLSX and CSV in one upload; validation flags and the review queue; missing fields stay null; **a model that invents values is blocked**; duplicates (same file, same invoice) and PDF↔Excel mismatch; batch PDF split into 3 invoices with page locations; manual correction re-validates and keeps history, approval; invalid corrections rejected; keyword, semantic and hybrid search with filters; page text, page image, original download, delete; dashboard stats and meta |
| `test_failures.py` | 7 functions (11 cases) | Broken files fail with the right code (empty, random bytes, text named .jpg, password PDF, cut XLSX); unsupported and oversized files rejected at upload; too many files; AI outage → `AI_UNAVAILABLE` → bulk reprocess succeeds; single reprocess; AI client retries 503/429 then succeeds; gives up at once on 401 |
| `test_ops.py` | 6 | Excel export (all six sheets, values, highlighted review rows, issue codes) and filtered export; recovery sweeper requeues a stuck document and finishes it; a document that keeps crashing is failed after 3 attempts (no endless loop); RQ failure callback marks a timeout; system status endpoint |

## Latest result

`90 passed` · line coverage 87 % of `backend/app` · machine-readable results: `evaluation/results/test-results.xml`
(JUnit) and `evaluation/results/coverage.xml`.

## Bugs found by testing and evaluation (and fixed)

| Found by | Problem | Fix |
|---|---|---|
| Live smoke test | Second and later jobs in a worker failed with "prepared statement already exists" | Database connections are no longer shared across RQ's forked job processes |
| Test suite | A class field named `field` hid `dataclasses.field` | Renamed import |
| Test suite | A summary row with only an amount was read as an invoice | Rows need an invoice number, supplier or date |
| Evaluation run 1 | Percentage rounding tolerance hid wrong totals on large (BDT) amounts | Absolute tolerance only (2 cents + 0.5 cent per line) |
| Evaluation run 1 | Duplicate flag landed on the first copy | Flag goes to the later copy |
| Evaluation run 1 | An ambiguous date was resolved by the model's guess | Ambiguous printed dates always stay empty and flagged |
| Evaluation run 1 | "$" was flagged as unproven currency | Currency proof accepts symbols |
| Evaluation run 3 / live check | OCR read a "3" as "2"; the image re-read copied the OCR text's mistake | The image reading no longer sees the OCR text (independent reading) |
| Live check | Half of the requests through the proxy failed (502), blocking log-in | Test containers no longer inherit the API's proxy labels; the web app retries transient errors and only rejects a code on HTTP 401 |
| Live check | Keep-alive race between proxy and API caused occasional 502 | API keep-alive set longer than the proxy's idle timeout |
| Live 1,000-page run | A deployment restarted workers in the middle of a job; the failure callback crashed when called from the sweeper thread | Workers finish their job before restarting; sweeper no longer triggers callbacks; dead jobs are detected and requeued within minutes; AI answers are cached so the restart resumes |
| Evaluation run 4 | An empty line-item reading "passed" the arithmetic and won the reconciliation | Complete line items always beat empty or amount-less ones |
