# Database schema

PostgreSQL 16 with the `vector` (pgvector) and `pg_trgm` extensions. Tables are defined in
[`backend/app/models.py`](../backend/app/models.py) and created at start-up (`init_db`, idempotent, with small
forward-only migrations).

```mermaid
erDiagram
    documents ||--o{ document_pages : "has"
    documents ||--o{ invoices : "contains"
    documents ||--o{ validation_issues : "has (file-level)"
    documents ||--o{ processing_events : "history"
    invoices ||--o{ validation_issues : "has"
    invoices ||--o{ corrections : "edited by people"
    invoices ||--o{ cross_checks : "compared (a)"
    invoices ||--o{ cross_checks : "compared (b)"

    documents {
        uuid id PK
        text filename
        text file_type "pdf | image | xlsx | xls | csv"
        text sha256 "duplicate-file detection"
        text status "queued | processing | completed | needs_review | failed"
        jsonb progress "stage, done, total"
        int page_count
        text text_method "digital | ocr | mixed | spreadsheet"
        float ocr_confidence
        int invoice_count
        int issue_count
        text error_code
        text error_message
        int attempts
        int ai_calls
        timestamptz created_at
        timestamptz started_at
        timestamptz heartbeat_at "last sign of life from the worker"
        timestamptz finished_at
        int processing_ms
        text full_text "deferred"
        tsvector text_tsv "generated, GIN"
    }
    document_pages {
        int id PK
        uuid document_id FK
        int page_no
        text label "sheet name"
        text method "digital | ocr | spreadsheet | error"
        text text
        float ocr_confidence
        int rotation
        float deskew_angle
    }
    invoices {
        uuid id PK
        uuid document_id FK
        int seq
        text source_kind "document | record (spreadsheet row)"
        jsonb location "pages or sheet + row"
        text invoice_number
        date invoice_date
        text supplier_name
        text customer_name
        numeric subtotal
        numeric tax
        numeric total
        char currency "ISO 4217"
        jsonb line_items
        jsonb fields "per field: value, evidence, verified, confidence, source, suggested"
        text extraction_method "llm_text | llm_dual | llm_vision | spreadsheet_columns"
        text model
        float confidence
        text status "ok | needs_review | reviewed"
        bool needs_review
        text invoice_number_norm "matching key"
        text supplier_norm "matching key"
        text search_text
        tsvector search_tsv "generated, GIN"
        vector embedding "1536, HNSW cosine"
        jsonb raw_ai_output "deferred"
    }
    validation_issues {
        int id PK
        uuid document_id FK
        uuid invoice_id FK "null = file-level"
        text code
        text severity "error | warning | info"
        text field
        text message
        jsonb details
    }
    corrections {
        int id PK
        uuid invoice_id FK
        text field
        jsonb old_value
        jsonb new_value
        text reason
        text corrected_by
        timestamptz created_at
    }
    cross_checks {
        int id PK
        uuid invoice_a FK
        uuid invoice_b FK
        text kind "pdf_excel, pdf_pdf, ..."
        text status "match | mismatch | duplicate"
        jsonb differences
    }
    processing_events {
        int id PK
        uuid document_id FK
        text stage
        text status "started | completed | failed | info"
        text message
        int duration_ms
        timestamptz created_at
    }
```

## Indexes and search

| Index | Purpose |
|---|---|
| `documents(sha256)`, `documents(status)`, `documents(created_at)` | duplicate files, list filters, ordering |
| `documents.text_tsv` (GIN) | keyword search inside every page of every document |
| `invoices.search_tsv` (GIN) | keyword search over invoice number, parties, items, totals |
| `invoices.supplier_name` (GIN, trigram) | fuzzy supplier search ("Northwnd" still finds "Northwind") |
| `invoices.embedding` (HNSW, cosine) | semantic search ("medical gloves" finds "Nitrile gloves, box of 100") |
| `invoices(invoice_number_norm)`, `invoices(supplier_norm)` | duplicate and cross-document matching |

**Hybrid search** ranks keyword and semantic results with Reciprocal Rank Fusion (k = 60), so results that match
both the words and the meaning come first.

## Why each table exists (requirement mapping)

| Brief asks to store | Where |
|---|---|
| Document metadata | `documents` |
| Extracted text | `document_pages.text`, `documents.full_text` |
| Structured results | `invoices` (columns + `fields` with evidence and confidence + `line_items`) |
| Validation errors | `validation_issues` |
| Processing history | `processing_events` (every stage with duration), `corrections` (every manual change) |
