# AI prompts and disclosure of AI-assisted development

## 1. Prompts used by the system

Source: [`backend/app/ai/prompts.py`](../backend/app/ai/prompts.py), prompt version `extract-v3`.
Models: `gpt-4.1-mini` for text and image readings (temperature 0, strict JSON schema), `text-embedding-3-small`
for search vectors. Requests are sent with `store: false`.

### Extraction (system prompt, verbatim)

```text
You extract invoice data from business documents for an accounts team.
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
10. notes: briefly mention anything uncertain (unreadable parts, conflicting totals); otherwise null.
```

The user message is the document text (PDF text, OCR text, or a sheet as `cell | cell` rows).

### Second, independent reading for scans (added to the user message, with the page images)

```text
The document is provided only as page images (an independent reading: no OCR text is given).
Read every value directly from the image. Evidence must be the text exactly as printed on the image.
```

### Output schema (strict)

Every field is `{value, evidence}` (the date also has `raw`); `line_items` is a list of
`{description, quantity, unit_price, amount, evidence}`; plus `document_kind` and `notes`. All keys are required and
nullable, so the model cannot omit a field or add a free-text field.

### What code does with the answer (no AI)

1. Evidence check: the quote must appear in the document text, and the value inside the quote. Otherwise the value
   becomes null and the invoice goes to review.
2. Normalisation: amounts to `Decimal`, dates from the printed form, ISO currency codes.
3. Reconciliation of the two readings for scans (agreement confirms; arithmetic settles amounts; otherwise flag).
4. All validation rules, duplicates and cross-checks.

## 2. Disclosure of AI-assisted development

This project was built by **Md Asif** with **Claude Code (Anthropic, Claude Opus model) as an AI pair programmer**.

| Who | What |
|---|---|
| Md Asif | Owned the project: requirements analysis, scope and priorities, product and UX decisions (formal typography, plain-language errors, Excel export, review flow, hosting choices), infrastructure access, review of every screen, acceptance of each step. |
| Claude Code (AI) | Wrote most of the source code, tests, dataset generator, evaluation script and documentation under Asif's direction, and ran the test and evaluation cycles. |
| Verification | Every part is covered by the automated test suite (run in CI) and by the measured evaluation on a labelled dataset. Problems found in evaluation runs were fixed and re-measured. The run history and the fixes are in [08-evaluation-report.md](08-evaluation-report.md). |

### Development prompts (summary)

The work was directed in plain language over one session. The main instructions:

1. "Read the assignment and explain every requirement; plan the implementation step by step."
2. "Host the processing on our existing server, the demo on Vercel; no personal domain; keep the OpenAI key out of
   the code; use existing resources."
3. "Implement every requirement professionally; the dashboard must be simple for a first-time user; errors must say
   what went wrong and what to do; add an Excel export."
4. "Use formal corporate fonts (Helvetica Neue, Manrope)."
5. "Accuracy target 100 % where verifiable: test, backtest, find and fix bugs in repeated cycles; handle failures and
   recovery."
6. "Improve OCR and PDF understanding; investigate login and error problems; separate private and submission files;
   document everything in GitHub."

The AI tools used at run time are limited to the OpenAI models named above.
