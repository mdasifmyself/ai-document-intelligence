# DocIntel evaluation: labelled dataset

Run: 2026-11-10T08:03:47+00:00 · models: gpt-4.1-mini (text), gpt-4.1-mini (vision), text-embedding-3-small (search)

| Metric | Result |
|---|---|
| Files processed | 96 |
| Document success rate (valid files) | 100.0% (90/90) |
| Document failure rate (valid files) | 0.0% |
| Broken/locked files handled politely | 100.0% of 6 |
| Invoices found | 141/141 (100.0%) |
| Field accuracy (all fields) | **99.8%** |
| Invoices with every field correct | 99.3% |
| Line items exactly right | 95.9% |
| Missing values left empty (not invented) | 100.0% |
| Planted problems caught | 55/55 |
| Clean invoices wrongly flagged | 7.6% (8/105) |
| Time per document (median / p95) | 4646 ms / 13466 ms |
| Throughput | 17.1 documents/min · 18.8 pages/min |

## Field accuracy

| Field | Accuracy |
|---|---|
| invoice_number | 99.3% |
| invoice_date | 100.0% |
| supplier_name | 100.0% |
| customer_name | 99.3% |
| subtotal | 100.0% |
| tax | 100.0% |
| total | 100.0% |
| currency | 100.0% |

## By file type

| Kind | Files | Field accuracy | Median time |
|---|---|---|---|
| corrupted | 5 | None% | 91 ms |
| csv_eu | 1 | 100.0% | 2542 ms |
| csv_us | 1 | 100.0% | 1235 ms |
| image_photo | 8 | 100.0% | 9868 ms |
| image_png | 5 | 100.0% | 6355 ms |
| image_poor | 4 | 93.8% | 8157 ms |
| image_tiff | 2 | 100.0% | 10069 ms |
| locked | 1 | None% | 100 ms |
| pdf_ambiguous_date | 2 | 100.0% | 3502 ms |
| pdf_bad_line | 4 | 100.0% | 4197 ms |
| pdf_batch | 2 | 100.0% | 11885 ms |
| pdf_conflict | 1 | 100.0% | 5014 ms |
| pdf_digital | 30 | 100.0% | 3904 ms |
| pdf_duplicate | 2 | 100.0% | 11740 ms |
| pdf_no_customer | 3 | 100.0% | 3537 ms |
| pdf_no_date | 3 | 100.0% | 5600 ms |
| pdf_no_tax | 2 | 100.0% | 5418 ms |
| pdf_scanned | 12 | 100.0% | 10024 ms |
| pdf_wrong_total | 5 | 100.0% | 4312 ms |
| xls_register | 1 | 100.0% | 1268 ms |
| xlsx_layout | 1 | 100.0% | 3946 ms |
| xlsx_ledger | 1 | 100.0% | 3426 ms |

## Planted problems

| Problem | Caught |
|---|---|
| AMBIGUOUS_DATE | 100.0% |
| CROSS_CHECK_MISMATCH | 100.0% |
| DUPLICATE_INVOICE | 100.0% |
| LEDGER_MATCH | 100.0% |
| LINE_ITEMS_MISMATCH | 100.0% |
| LINE_ITEM_MATH | 100.0% |
| MISSING_FIELD | 100.0% |
| READ_FROM_IMAGE | 100.0% |
| TOTAL_MISMATCH | 100.0% |

False flags on clean invoices: READ_FROM_IMAGE ×6, LINE_ITEM_MATH ×2, LINE_ITEMS_MISMATCH ×1

## Every wrong field

| File | Invoice | Wrong fields |
|---|---|---|
| poor_02_BL-20260071.jpg | BL-20260071 | invoice_number, customer_name |
