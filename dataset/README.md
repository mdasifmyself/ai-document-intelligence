# Labelled dataset

`generate.py` builds the evaluation dataset with a known correct answer for every file (seed 42, fully reproducible).
All companies are fictional.

```bash
pip install -r backend/requirements-dev.txt
python dataset/generate.py --out dataset/out           # 96 files + labels.json
python dataset/generate.py --out dataset/out --big     # + a 1,000-page batch PDF (789 invoices)
python dataset/generate.py --samples --out dataset/samples   # the 12 demo sample files
```

## What is inside (96 files, 141 invoices)

| Group | Files | Purpose |
|---|---|---|
| Digital PDFs, three layouts and label wordings | 30 | baseline extraction |
| Planted problems in digital PDFs | 19 | wrong totals (5), wrong line amounts (4), no date (3), no customer (3), no tax line (2), ambiguous dates (2) |
| Scanned PDFs (rotation, noise, blur, JPEG artefacts) | 12 | OCR path |
| Phone photos (perspective, shadow, blur) | 8 | OCR on photos |
| Very poor photos (low resolution, heavy blur, low contrast) | 4 | uncertainty must be flagged |
| Clean PNG images | 5 | image path |
| Multi-page TIFF (2 invoices each) | 2 | multi-frame images, splitting |
| Batch PDFs (6 invoices each, one invoice spans 2 pages) | 2 | splitting multi-invoice PDFs |
| Duplicates (re-sent PDF, scanned copy) and a conflicting revision | 3 | duplicate and PDF↔PDF conflict detection |
| Excel ledger (3 sheets: invoices, line items, summary) | 1 | spreadsheet columns, PDF↔Excel cross-checks (11 matches, 3 mismatches), duplicate row, missing number, wrong total |
| Legacy XLS register, US and EU CSV exports (`;`, decimal comma, `dd.mm.yyyy`) | 3 | formats and number styles |
| Invoice laid out in a spreadsheet like a printed form | 1 | AI on spreadsheet text |
| Broken and locked files (truncated PDF, random bytes, empty PNG, cut XLSX, password PDF, text renamed .jpg) | 6 | must fail politely |

`labels.json` lists, per file, the expected status, the expected error code for broken files, and for every invoice
the correct values of all fields and line items plus the problems the system is expected to flag.
