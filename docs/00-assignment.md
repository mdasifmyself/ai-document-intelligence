# The assignment

This is the brief this project answers: **AI Engineer, Project: AI-Powered Document Intelligence System**, five-day
take-home. The brief is restated here so the repository is self-contained. Contact details from the invitation email
are left out on purpose.

## Scenario

A company receives thousands of business documents daily: financial data including invoices, receipts, scanned
PDFs, images, Excel spreadsheets and CSV files (PDFs of about 1,000 pages). Employees manually extract invoice
details, verify financial calculations, enter the information into internal systems, and cross-verify PDF against
PDF and PDF against Excel. This is time-consuming and error-prone. The company wants an AI-powered document
intelligence system that automates document processing, extracts structured information, validates results, and
makes the data searchable through an API and a web interface.

## Tasks

| # | Task | Requirement |
|---|---|---|
| 1 | Document processing | Accept multiple PDF, JPG, PNG, TIFF, XLSX, XLS and CSV files. Extract text from digital PDFs, use OCR for scanned documents and images, parse structured spreadsheet data. Handle multi-page PDFs, multiple sheets, poor image quality and corrupted files. |
| 2 | AI information extraction | Extract invoice number, invoice date, supplier name, customer name, subtotal, tax, total, currency and line items. Return structured JSON and handle missing or uncertain information without inventing values. |
| 3 | Data validation | Identify missing fields, incorrect numeric values, duplicate invoices, and inconsistencies between subtotal, tax, line items and total. Flag records requiring manual review. |
| 4 | Backend API | REST APIs for document uploads, processing status, extracted results, document search, manual corrections and failed-job reprocessing. Background processing for time-consuming OCR and AI operations. |
| 5 | Database and search | Store document metadata, extracted text, structured results, validation errors and processing history. Keyword-based filtering and semantic search. |
| 6 | Frontend | A simple React or Next.js interface to upload multiple documents, monitor processing progress, inspect extracted information, review validation errors, correct values and search previously processed documents. |
| 7 | Testing and evaluation | Automated tests for document processing, OCR, spreadsheet parsing, AI extraction, validation, API endpoints and failure scenarios. Evaluate with a labelled dataset and report actual extraction accuracy, processing time, document success rate and failure rate. |

**Suggested technologies:** React/Next.js, Node.js/NestJS, Python-based OCR tools, pandas/openpyxl, an LLM API,
PostgreSQL or MongoDB, Redis/BullMQ, a vector database. Alternatives are allowed with an explanation of the design
decisions.

## Deliverables

1. Git repository containing the source code
2. README and setup instructions
3. Architecture diagram and database schema
4. Working backend API and frontend
5. PDF, image, Excel and CSV processing pipelines
6. Automated tests and test results
7. Evaluation report with actual measured metrics
8. Recorded walkthrough of the working application
9. AI prompts and disclosure of AI-assisted development, where applicable

Non-functional expectations: smooth performance, high speed, scalability, reliability and strong security.

Each item is mapped to its implementation and evidence in [01-requirements-checklist.md](01-requirements-checklist.md).
