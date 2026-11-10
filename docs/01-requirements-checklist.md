# Requirements checklist

Every line of the brief ([00-assignment.md](00-assignment.md)) with where it is implemented and how it was verified.
Status ✅ = implemented and verified by an automated test, the measured evaluation or a live check.

## Task 1: Document processing

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Accept multiple files | `POST /api/v1/documents` takes up to 50 files per request; drag-and-drop multi-upload in the web app | `test_api::test_scanned_and_photo_and_spreadsheet` (4 files in one upload); evaluation uploads 96 files in batches | ✅ |
| PDF, JPG, PNG, TIFF, XLSX, XLS, CSV | Type detected from file bytes (`pipeline/detect.py`) | `test_units::test_detect_by_content`, evaluation covers all seven types | ✅ |
| Text from digital PDFs | PDFium text layer per page (`pipeline/readers.py`) | `test_readers::test_digital_pdf_uses_text_layer`; evaluation: 30 digital PDFs at 100 % | ✅ |
| OCR for scanned documents and images | Pages without a text layer are rendered at 300 dpi; Tesseract 5 after OpenCV clean-up (`pipeline/ocr.py`); scans also get an independent image reading (`extract.reconcile`) | `test_readers::test_scanned_pdf_goes_to_ocr`, `test_noisy_jpeg_and_multipage_tiff`; evaluation: scanned PDFs, photos, PNG, TIFF | ✅ |
| Parse structured spreadsheet data | Every sheet; header synonyms + fuzzy matching map columns; line-item sheets join by invoice number; form-like sheets go to AI (`pipeline/spreadsheets.py`) | `test_readers::test_xlsx_register_with_line_items_and_extra_sheet`, `test_xls_and_eu_csv`; evaluation: ledger, XLS, 2 CSV, form sheet at 100 % | ✅ |
| Multi-page PDFs | Page-by-page reading; long PDFs split into invoices by number and page markers (`pipeline/segment.py`) | `test_units::test_split_multi_invoice_batch`, `test_api::test_batch_pdf_is_split_into_invoices`; 1,000-page batch | ✅ |
| Multiple sheets | All sheets read, each shown in the viewer; register + line items + summary handled | `test_readers::test_xlsx_register_with_line_items_and_extra_sheet` | ✅ |
| Poor image quality | Orientation fix, deskew, contrast, denoise, second OCR pass; dual reading; uncertain values flagged | `test_readers::test_ocr_fixes_sideways_photo`; evaluation: 4 very poor photos (flagged for review as expected) | ✅ |
| Corrupted files | Detected and failed with stable codes and a "What to do" message; damaged pages and truncated images handled with warnings | `test_failures::test_broken_files_fail_politely` (5 cases), `test_readers::test_damaged_image_is_read_with_warning`; evaluation: 6/6 broken files handled | ✅ |

## Task 2: AI information extraction

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Invoice number, date, supplier, customer, subtotal, tax, total, currency, line items | Strict JSON-schema output (`ai/prompts.py`), normalised (`pipeline/normalize.py`) | evaluation: field accuracy per field (see report) | ✅ |
| Structured JSON | `GET /documents/{id}`, `GET /invoices/{id}`; JSON tab in the web app | `test_api::test_upload_digital_pdf_end_to_end` | ✅ |
| Handle missing information without inventing values | Evidence guard (`pipeline/evidence.py`): unproven values become null; ambiguous dates stay empty | `test_api::test_missing_fields_are_null_not_invented`, `test_model_inventing_a_value_is_blocked`; evaluation: 0 invented values | ✅ |
| Handle uncertain information | Confidence per field; "read from the image", "two readings differ", "could not be proven" flags with the AI's suggestion shown | `test_units::test_unresolvable_disagreement_is_flagged_with_both_readings` | ✅ |

## Task 3: Data validation

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Missing fields | Required (error) vs expected (warning); spreadsheet rows checked only for their columns | `test_units::test_missing_required_and_expected_fields`; evaluation: MISSING_FIELD 100 % | ✅ |
| Incorrect numeric values | Negative / unrealistic amounts, unusual tax rate, future or invalid dates | `test_units::test_negative_and_future_and_unusual_tax` | ✅ |
| Duplicate invoices | Same supplier + number (later copy flagged), same file fingerprint, near-duplicates (same supplier, date and total) | `test_api::test_duplicates_and_cross_checks`; evaluation: DUPLICATE_INVOICE 100 % | ✅ |
| Subtotal / tax / line items / total consistency | Exact Decimal maths with a 2-cent + per-line rounding tolerance | `test_units::test_total_mismatch`, `test_line_item_math_and_sum`; evaluation: TOTAL_MISMATCH, LINE_ITEMS_MISMATCH, LINE_ITEM_MATH 100 % | ✅ |
| PDF ↔ PDF and PDF ↔ Excel cross-verification (from the scenario) | `pipeline/matching.py`, Cross-checks page and API | `test_api::test_duplicates_and_cross_checks`; evaluation: CROSS_CHECK_MISMATCH 100 % | ✅ |
| Flag records requiring manual review | `needs_review` + status; review queue; badge in navigation | `test_api::test_validation_flags_and_review_queue` | ✅ |

## Task 4: Backend API

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Document uploads | `POST /documents` (202 + ids, rejected list) | `test_api`, `test_failures::test_unsupported_and_oversize_are_rejected_at_upload` | ✅ |
| Processing status | `GET /documents/{id}/status`, live stage and progress | `test_api::test_upload_digital_pdf_end_to_end` | ✅ |
| Extracted results | `GET /documents/{id}`, `GET /invoices`, `GET /invoices/{id}`, `GET /export.xlsx` | `test_api`, `test_ops::test_excel_export_*` | ✅ |
| Document search | `GET /search` (keyword / semantic / hybrid + filters), `GET /documents?q=` | `test_api::test_search_keyword_semantic_and_filters` | ✅ |
| Manual corrections | `PATCH /invoices/{id}` (history, re-validation), `POST /invoices/{id}/approve` | `test_api::test_manual_correction_revalidates_and_keeps_history` | ✅ |
| Failed-job reprocessing | `POST /documents/{id}/reprocess`, `POST /jobs/reprocess-failed`, `GET /jobs/failed` | `test_failures::test_ai_outage_then_reprocess`, `test_single_reprocess_endpoint` | ✅ |
| Background processing for OCR and AI | Redis + RQ workers; upload returns at once; failure callback; recovery sweeper | `test_ops::test_stuck_document_is_requeued_automatically`, `test_temporary_failure_is_retried_once_automatically`, `test_forked_process_uses_its_own_database_connections` | ✅ |

## Task 5: Database and search

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Document metadata | `documents` table | [03-database-schema.md](03-database-schema.md) | ✅ |
| Extracted text | `document_pages.text`, `documents.full_text` | `GET /documents/{id}/pages/{n}` test | ✅ |
| Structured results | `invoices` (+ per-field evidence, confidence, source) | API tests | ✅ |
| Validation errors | `validation_issues` | API tests | ✅ |
| Processing history | `processing_events` (every stage with duration), `corrections` | `test_api::test_upload_digital_pdf_end_to_end` (stages present) | ✅ |
| Keyword-based filtering | PostgreSQL full-text (GIN) + trigram + filters (supplier, currency, dates, amounts, review status, file type) | search tests | ✅ |
| Semantic search | pgvector embeddings (HNSW, cosine), hybrid with Reciprocal Rank Fusion | `test_api::test_search_keyword_semantic_and_filters` | ✅ |

## Task 6: Frontend

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| React or Next.js | Next.js 16 on Vercel | https://docintel-invoice-ai.vercel.app | ✅ |
| Upload multiple documents | Upload page: drag and drop, file list, progress bar; sample files | live check | ✅ |
| Monitor processing progress | Live stage and progress per file; dashboard "being processed"; System health | live check | ✅ |
| Inspect extracted information | Document detail: page viewer + fields with proof quotes, confidence, line items, JSON | live check | ✅ |
| Review validation errors | "Needs your attention" with What to do; review queue | live check | ✅ |
| Correct values | Edit → save (re-validates) → Approve; history | live check + API test | ✅ |
| Search previously processed documents | Search page (3 modes, filters, export) and Documents search | live check | ✅ |

## Task 7: Testing and evaluation

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Tests: document processing, OCR, spreadsheet parsing | `test_readers.py`, `test_units.py` | 93 passed | ✅ |
| Tests: AI extraction, validation | `test_api.py` (fake model incl. a "lying" model), `test_units.py` | 93 passed | ✅ |
| Tests: API endpoints, failure scenarios | `test_api.py`, `test_failures.py`, `test_ops.py` | 93 passed | ✅ |
| Labelled dataset | `dataset/generate.py` (96 files + answer key; 1,000-page batch) | `dataset/README.md` | ✅ |
| Report actual accuracy, processing time, success rate, failure rate | `evaluation/run_eval.py` against the live system | [08-evaluation-report.md](08-evaluation-report.md) | ✅ |

## Deliverables

| # | Deliverable | Where | Status |
|---|---|---|---|
| 1 | Git repository with source code | this repository | ✅ |
| 2 | README and setup instructions | [README.md](../README.md), [06-setup-and-deployment.md](06-setup-and-deployment.md) | ✅ |
| 3 | Architecture diagram and database schema | [02-architecture.md](02-architecture.md), [03-database-schema.md](03-database-schema.md) | ✅ |
| 4 | Working backend API and frontend | live demo + `/api/docs` | ✅ |
| 5 | PDF, image, Excel and CSV pipelines | `backend/app/pipeline/` | ✅ |
| 6 | Automated tests and test results | `backend/tests/`, `evaluation/results/test-results.xml`, CI | ✅ |
| 7 | Evaluation report with actual measured metrics | [08-evaluation-report.md](08-evaluation-report.md) | ✅ |
| 8 | Recorded walkthrough of the working application | link in the submission email | recorded separately |
| 9 | AI prompts and disclosure of AI-assisted development | [09-ai-prompts-and-disclosure.md](09-ai-prompts-and-disclosure.md) | ✅ |

## Non-functional expectations

| Expectation | How |
|---|---|
| Smooth performance, high speed | Upload returns at once; parallel AI calls; heavy columns loaded only on demand; median time per file in the report |
| Scalability | Stateless API, horizontally scalable workers, queue absorbs bursts ([02-architecture.md](02-architecture.md#scaling)) |
| Reliability | Retries, failure callback, recovery sweeper, resumable jobs, graceful worker restarts ([11-operations-and-recovery.md](11-operations-and-recovery.md)) |
| Strong security | [10-security.md](10-security.md) |

## Extra features beyond the brief

Excel export (formatted, filtered) · dual reading of scans with reconciliation · "What to do" guidance for every
problem · System health page (workers, backlog, AI budget, failures, recoveries) · automatic recovery and resumable
jobs · sample files for a one-click demo · start-here guide for first-time users · interactive API documentation ·
AI key kept outside the code (n8n gateway) · daily AI budget.
