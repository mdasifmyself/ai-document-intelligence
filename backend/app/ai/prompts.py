"""Prompts and the JSON schema used for invoice extraction. Shown in full in docs/09-ai-prompts-and-disclosure.md."""

PROMPT_VERSION = "extract-v3"

EXTRACTION_SYSTEM = """You extract invoice data from business documents for an accounts team.
The text comes from PDF text extraction, OCR (which can contain reading errors) or a spreadsheet.

Rules:
1. Use only what is printed in the document. Never guess, infer, look up or calculate a value.
2. If a field is not printed, or you cannot read it with certainty, set its value AND evidence to null.
   A null is always better than a plausible-looking guess.
3. For every value you return, copy into "evidence" the exact snippet of the document where you found it
   (verbatim, up to 120 characters, ideally including the printed label, e.g. "Invoice No: INV-2041").
4. Amounts: return plain numbers as printed (no currency symbol, no thousands separator, "." as decimal point).
   Do not add, multiply or round anything. If the printed total looks wrong, still return the printed total.
5. invoice_date: "raw" is the date exactly as printed. "value" is the same date as YYYY-MM-DD only when the
   day and month are unambiguous (e.g. "14/03/2026", "March 4, 2026", "2026-03-04"). If a numeric date could be
   read both ways (e.g. "03/04/2026"), set value to null and keep raw.
6. currency: an ISO 4217 code. Use a printed code if there is one. Symbols: "$" alone = USD, "€" = EUR,
   "£" = GBP, "৳" or "Tk" = BDT. If nothing indicates the currency, null.
7. supplier_name = the business that issued the invoice (seller, "From", letterhead).
   customer_name = the party being billed ("Bill to", "Customer", "Sold to").
8. line_items: one entry per product or service row. Do not include subtotal, tax, discount or total rows.
9. document_kind: "invoice", "receipt", "credit_note" or "other" (not a financial document).
10. notes: briefly mention anything uncertain (unreadable parts, conflicting totals); otherwise null."""

VISION_HINT = ("The document is provided only as page images (an independent reading: no OCR text is given). "
               "Read every value directly from the image. Evidence must be the text exactly as printed on the image.")


def _nullable(t):
    return {"type": [t, "null"]}


def _field(value_type: str) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["value", "evidence"],
            "properties": {"value": _nullable(value_type), "evidence": _nullable("string")}}


EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_kind", "invoice_number", "invoice_date", "supplier_name", "customer_name",
                 "subtotal", "tax", "total", "currency", "line_items", "notes"],
    "properties": {
        "document_kind": {"type": "string", "enum": ["invoice", "receipt", "credit_note", "other"]},
        "invoice_number": _field("string"),
        "invoice_date": {"type": "object", "additionalProperties": False, "required": ["value", "raw", "evidence"],
                         "properties": {"value": _nullable("string"), "raw": _nullable("string"),
                                        "evidence": _nullable("string")}},
        "supplier_name": _field("string"),
        "customer_name": _field("string"),
        "subtotal": _field("number"),
        "tax": _field("number"),
        "total": _field("number"),
        "currency": _field("string"),
        "line_items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["description", "quantity", "unit_price", "amount", "evidence"],
            "properties": {"description": {"type": "string"}, "quantity": _nullable("number"),
                           "unit_price": _nullable("number"), "amount": _nullable("number"),
                           "evidence": _nullable("string")}}},
        "notes": _nullable("string"),
    },
}
