# DocIntel evaluation: labelled dataset

Run: 2026-11-10T09:35:15+00:00 · models: gpt-4.1-mini (text), gpt-4.1-mini (vision), text-embedding-3-small (search)

| Metric | Result |
|---|---|
| Files processed | 96 |
| Document success rate (valid files) | 100.0% (90/90) |
| Document failure rate (valid files) | 0.0% |
| Broken/locked files handled politely | 100.0% of 6 |
| Invoices found | 141/141 (100.0%) |
| Field accuracy (all fields) | **100.0%** |
| Invoices with every field correct | 100.0% |
| Line items exactly right | 99.0% |
| Missing values left empty (not invented) | 100.0% |
| Planted problems caught | 55/55 |
| Clean invoices wrongly flagged | 5.7% (6/105) |
| Time per document (median / p95) | 4965 ms / 15783 ms |
| Throughput | 14.0 documents/min · 15.5 pages/min |

## Field accuracy

| Field | Accuracy |
|---|---|
| invoice_number | 100.0% |
| invoice_date | 100.0% |
| supplier_name | 100.0% |
| customer_name | 100.0% |
| subtotal | 100.0% |
| tax | 100.0% |
| total | 100.0% |
| currency | 100.0% |

## By file type

| Kind | Files | Field accuracy | Median time |
|---|---|---|---|
| corrupted | 5 | None% | 97 ms |
| csv_eu | 1 | 100.0% | 2752 ms |
| csv_us | 1 | 100.0% | 4180 ms |
| image_photo | 8 | 100.0% | 10710 ms |
| image_png | 5 | 100.0% | 9108 ms |
| image_poor | 4 | 100.0% | 10646 ms |
| image_tiff | 2 | 100.0% | 16496 ms |
| locked | 1 | None% | 114 ms |
| pdf_ambiguous_date | 2 | 100.0% | 3976 ms |
| pdf_bad_line | 4 | 100.0% | 4611 ms |
| pdf_batch | 2 | 100.0% | 11541 ms |
| pdf_conflict | 1 | 100.0% | 4518 ms |
| pdf_digital | 30 | 100.0% | 4128 ms |
| pdf_duplicate | 2 | 100.0% | 7428 ms |
| pdf_no_customer | 3 | 100.0% | 3845 ms |
| pdf_no_date | 3 | 100.0% | 5000 ms |
| pdf_no_tax | 2 | 100.0% | 4962 ms |
| pdf_scanned | 12 | 100.0% | 14914 ms |
| pdf_wrong_total | 5 | 100.0% | 4786 ms |
| xls_register | 1 | 100.0% | 1813 ms |
| xlsx_layout | 1 | 100.0% | 5788 ms |
| xlsx_ledger | 1 | 100.0% | 3683 ms |

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

False flags on clean invoices: READ_FROM_IMAGE ×6
