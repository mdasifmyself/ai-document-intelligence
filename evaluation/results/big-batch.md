# DocIntel evaluation: 1,000-page batch PDF

Run: 2026-11-10T09:56:06+00:00 · models: gpt-4.1-mini (text), gpt-4.1-mini (vision), text-embedding-3-small (search)

| Metric | Result |
|---|---|
| Files processed | 1 |
| Document success rate (valid files) | 100.0% (1/1) |
| Document failure rate (valid files) | 0.0% |
| Broken/locked files handled politely | None% of 0 |
| Invoices found | 789/789 (100.0%) |
| Field accuracy (all fields) | **100.0%** |
| Invoices with every field correct | 100.0% |
| Line items exactly right | 100.0% |
| Missing values left empty (not invented) | None% |
| Planted problems caught | 0/0 |
| Clean invoices wrongly flagged | 0.0% (0/789) |
| Time per document (median / p95) | 1036731 ms / 1036731 ms |
| Throughput | 0.1 documents/min · 57.8 pages/min |

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
| pdf_big_batch | 1 | 100.0% | 1036731 ms |

## Planted problems

| Problem | Caught |
|---|---|
