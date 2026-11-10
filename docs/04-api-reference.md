# API reference

Interactive documentation (try every endpoint in the browser): **`/api/docs`** on the demo,
for example https://docintel-invoice-ai.vercel.app/api/docs. The OpenAPI schema is at `/api/openapi.json`.

All endpoints are under `/api/v1`. Send the access code in the header `X-Access-Code: <code>`
(or `Authorization: Bearer <code>`). `/health` and `/meta` are open.

## Endpoints

| Method | Path | What it does |
|---|---|---|
| POST | `/documents` | Upload 1–50 files (multipart field `files`). Returns **202** at once with document ids; processing runs in the background. Unsupported or oversized files are listed in `rejected`. |
| GET | `/documents` | List documents. Filters: `status` (comma list), `file_type`, `q` (keyword in file name or text), `batch_id`, `ids`, `page`, `page_size`. |
| GET | `/documents/{id}` | Everything about one document: pages, invoices (with issues and corrections), file-level issues, processing history. |
| GET | `/documents/{id}/status` | Light status for polling: status, stage, done/total, counts, error code. |
| GET | `/documents/{id}/file` | Download the original file. |
| GET | `/documents/{id}/pages/{n}` | Text of one page or sheet, with the reading method and OCR confidence. |
| GET | `/documents/{id}/pages/{n}/image` | PNG preview of a PDF or image page. |
| POST | `/documents/{id}/reprocess` | Run the document again (for example after an AI outage). |
| DELETE | `/documents/{id}` | Delete the document, its results and its files. |
| GET | `/invoices` | List invoices. Filters: `needs_review`, `status`, `supplier`, `currency`, `document_id`, `issue_code`, `date_from`, `date_to`, `min_total`, `max_total`. Each item includes `issue_codes`. |
| GET | `/invoices/{id}` | One invoice with issues and correction history. |
| PATCH | `/invoices/{id}` | Manual correction: `{"fields": {"total": "1150.00"}, "reason": "...", "corrected_by": "..."}`. Saves old and new values, then re-runs validation and cross-checks. |
| POST | `/invoices/{id}/approve` | Mark as reviewed by a person. |
| GET | `/search` | `q`, `mode` = `hybrid` (default) \| `keyword` \| `semantic`, plus the invoice filters. Returns hits with score, match type and highlighted snippet. |
| GET | `/cross-checks` | Pairs of the same invoice in two documents. Filters: `status` (`match`, `mismatch`, `duplicate`), `kind` (`pdf_excel`, `pdf_pdf`, …). |
| GET | `/export.xlsx` | Formatted Excel workbook (Summary, Invoices, Line items, Issues, Cross-checks, Documents). Accepts the invoice filters and `status`, `document_id`. |
| GET | `/jobs/failed` | Failed documents. |
| POST | `/jobs/reprocess-failed` | Re-queue every failed document (optionally `codes=AI_UNAVAILABLE,...`). |
| GET | `/jobs/queue` | Queue depth and counts by status. |
| GET | `/system/status` | Workers, backlog, AI service state and budget, stuck files, recent failures and recoveries. |
| GET | `/stats` | Dashboard numbers. |
| GET | `/samples`, POST `/samples/load` | List or process the built-in sample files. |
| GET | `/health` | Database and queue status (open). |
| GET | `/meta` | Limits, allowed file types, model names, prompt version (open). |

## Example: upload, wait, read

```bash
API=https://docintel-invoice-ai.vercel.app/api/v1
CODE=your-access-code

# 1. upload two files
curl -s -H "X-Access-Code: $CODE" -F files=@invoice.pdf -F files=@ledger.xlsx $API/documents

# 2. poll one document until it is completed / needs_review / failed
curl -s -H "X-Access-Code: $CODE" $API/documents/<id>/status

# 3. read the structured result
curl -s -H "X-Access-Code: $CODE" $API/documents/<id>

# 4. correct a value and approve
curl -s -X PATCH -H "X-Access-Code: $CODE" -H "Content-Type: application/json" \
     -d '{"fields":{"total":"1150.00"},"reason":"misprint","corrected_by":"Reviewer"}' $API/invoices/<invoice-id>
curl -s -X POST -H "X-Access-Code: $CODE" "$API/invoices/<invoice-id>/approve?reviewer=Reviewer"

# 5. search and export
curl -s -H "X-Access-Code: $CODE" "$API/search?q=medical%20gloves&mode=hybrid"
curl -s -H "X-Access-Code: $CODE" -o export.xlsx "$API/export.xlsx?needs_review=true"
```

## Extracted invoice (JSON shape)

```json
{
  "invoice_number": "INV-20260041",
  "invoice_date": "2026-03-14",
  "supplier_name": "Northwind Medical Supplies Ltd",
  "customer_name": "Sunrise Home Care LLC",
  "subtotal": 1000.0, "tax": 150.0, "total": 1150.0, "currency": "USD",
  "line_items": [{"description": "Nitrile gloves, box of 100", "quantity": 10, "unit_price": 100.0, "amount": 1000.0}],
  "fields": {
    "total": {"value": 1150.0, "evidence": "Total Due USD 1,150.00", "verified": true,
              "confidence": 0.97, "source": "text"}
  },
  "extraction_method": "llm_text",
  "status": "ok", "needs_review": false,
  "issues": []
}
```

`fields.<name>.source` is `text` (proven in the document text), `vision+text` (two independent readings agree),
`vision` (read from the image only, flagged for a person), `cell` (spreadsheet cell, evidence like `Invoices!G12`)
or `manual` (corrected by a person). A value that could not be proven is `null`, with `verified: false` and the AI's
`suggested` value kept for the reviewer.

## Errors

Errors return JSON `{"detail": "plain-language message"}` with the usual status codes: 401 (access code), 404,
409 (document is being processed), 413 (too many or too large files), 422 (invalid value), 429 (rate limit).
Processing failures do not return errors. The document gets `status: failed` with a stable `error_code`
(`CORRUPTED_FILE`, `PASSWORD_PROTECTED`, `EMPTY_FILE`, `UNSUPPORTED_TYPE`, `TOO_MANY_PAGES`, `AI_UNAVAILABLE`,
`JOB_TIMEOUT`, `WORKER_LOST`, `INTERNAL_ERROR`) and a message. See [11-operations-and-recovery.md](11-operations-and-recovery.md).
