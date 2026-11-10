// Plain-English names for everything the API returns as a code.
export const STATUS: Record<string, { label: string; tone: string; hint: string }> = {
  queued: { label: "Waiting", tone: "neutral", hint: "In the queue. Processing starts in a moment." },
  processing: { label: "Processing", tone: "blue", hint: "Reading the file and extracting the data." },
  completed: { label: "Done", tone: "green", hint: "Everything was read and every check passed." },
  needs_review: { label: "Needs review", tone: "amber", hint: "Read successfully, but a person should check the flagged items." },
  failed: { label: "Failed", tone: "red", hint: "The file could not be processed. The reason is shown; you can retry." },
  ok: { label: "Checked", tone: "green", hint: "All checks passed." },
  reviewed: { label: "Approved", tone: "green", hint: "A person reviewed and approved this invoice." },
};

export const STAGE: Record<string, string> = {
  queued: "Waiting in queue", starting: "Starting", detect: "Checking the file", reading: "Reading pages",
  read: "Reading pages", split: "Finding invoices", extract: "Extracting with AI", extracting: "Extracting with AI",
  validate: "Checking numbers", match: "Looking for duplicates", index: "Making it searchable", done: "Done", failed: "Failed",
};

export const FIELD: Record<string, string> = {
  invoice_number: "Invoice number", invoice_date: "Invoice date", supplier_name: "Supplier", customer_name: "Customer",
  subtotal: "Subtotal", tax: "Tax", total: "Total", currency: "Currency", line_items: "Line items",
};

export const ISSUE: Record<string, { title: string; explain: string }> = {
  MISSING_FIELD: { title: "Missing value", explain: "A field was not printed on the document, so it was left empty instead of guessed." },
  UNVERIFIED_VALUE: { title: "Value could not be proven", explain: "The AI suggested a value but its quote was not found in the document, so the value was removed." },
  TOTAL_MISMATCH: { title: "Total does not add up", explain: "Subtotal plus tax is different from the printed total." },
  LINE_ITEMS_MISMATCH: { title: "Line items do not add up", explain: "The sum of the line items is different from the subtotal." },
  LINE_ITEM_MATH: { title: "Line calculation is wrong", explain: "Quantity × unit price is different from the line amount." },
  INVALID_AMOUNT: { title: "Impossible amount", explain: "An amount is negative or unrealistically large." },
  UNUSUAL_TAX_RATE: { title: "Unusual tax rate", explain: "The tax is a very high share of the subtotal." },
  AMBIGUOUS_DATE: { title: "Date can be read two ways", explain: "A date like 03/04/2026 could mean March 4 or April 3. Please confirm it." },
  FUTURE_DATE: { title: "Date in the future", explain: "The invoice date is later than today." },
  INVALID_DATE: { title: "Date looks wrong", explain: "The invoice date is not realistic." },
  LOW_OCR_QUALITY: { title: "Hard-to-read scan", explain: "The scan quality is low; check the values against the original." },
  READ_FROM_IMAGE: { title: "Read from the image", explain: "The text could not be read reliably, so the AI read the page image. Please confirm the values." },
  SELF_CHECK_REREAD: { title: "Re-read automatically", explain: "The numbers did not add up the first time, so the page was read again and the better result was kept." },
  DUPLICATE_INVOICE: { title: "Duplicate invoice", explain: "The same invoice (same supplier and number) was already received." },
  POSSIBLE_DUPLICATE: { title: "Possible duplicate", explain: "Same supplier, date and total as another invoice, but a different number." },
  DUPLICATE_FILE: { title: "Same file uploaded twice", explain: "This exact file was uploaded before." },
  CROSS_CHECK_MISMATCH: { title: "Does not match another document", explain: "The same invoice appears in another file with different values." },
  LEDGER_MATCH: { title: "Confirmed by another document", explain: "The same invoice in another file has identical values." },
  NOT_AN_INVOICE: { title: "Not an invoice", explain: "This page does not look like an invoice or receipt." },
  NO_TEXT_FOUND: { title: "No text found", explain: "No readable text was found in the file." },
  NO_INVOICE_DATA: { title: "No invoice data", explain: "The spreadsheet has no invoice columns or invoice-like sheets." },
  DAMAGED_FILE: { title: "Damaged file", explain: "The file is partly damaged; only the readable part was processed." },
  DAMAGED_PAGE: { title: "Damaged page", explain: "One page could not be read." },
  CORRUPTED_FILE: { title: "Damaged file", explain: "The file is broken and cannot be opened." },
  EMPTY_FILE: { title: "Empty file", explain: "The file has no content (0 bytes)." },
  UNSUPPORTED_TYPE: { title: "Unsupported file type", explain: "Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV." },
  PASSWORD_PROTECTED: { title: "Password-protected PDF", explain: "Upload an unlocked copy of the PDF." },
  TOO_MANY_PAGES: { title: "Too many pages", explain: "The file has more pages than the limit." },
  EMPTY_DOCUMENT: { title: "Empty document", explain: "The file has no pages or sheets." },
  AI_UNAVAILABLE: { title: "AI service unavailable", explain: "The AI service did not answer. Retry the document later." },
  INTERNAL_ERROR: { title: "Unexpected error", explain: "Something went wrong. Retry the document; if it fails again, check the history." },
  FILE_TOO_LARGE: { title: "File too large", explain: "The file is larger than the upload limit." },
};

export const METHOD: Record<string, string> = {
  digital: "Text layer", ocr: "OCR", mixed: "Text + OCR", spreadsheet: "Spreadsheet", vision: "AI vision",
  llm_text: "AI from text", llm_vision: "AI from image", llm_dual: "Two AI readings (text + image)", spreadsheet_columns: "Spreadsheet columns",
};

export const KIND: Record<string, string> = {
  pdf_pdf: "PDF ↔ PDF", pdf_excel: "PDF ↔ Excel", pdf_csv: "PDF ↔ CSV", pdf_image: "PDF ↔ Image", image_image: "Image ↔ Image",
  image_excel: "Image ↔ Excel", image_csv: "Image ↔ CSV", excel_excel: "Excel ↔ Excel", excel_csv: "Excel ↔ CSV", csv_csv: "CSV ↔ CSV",
};

export const issueTitle = (code: string) => ISSUE[code]?.title || code.replace(/_/g, " ").toLowerCase();

// What a person should do about each problem: shown under the problem as "What to do".
export const ACTION: Record<string, string> = {
  MISSING_FIELD: "Look at the page. If the value is printed, press Edit and type it in. If it is really missing, ask the supplier or approve as it is.",
  UNVERIFIED_VALUE: "Find the value on the page. If it is there, press Edit and enter it; it will be saved as checked by you.",
  TOTAL_MISMATCH: "Compare subtotal, tax and total on the page. If the reading is wrong, correct it. If the printed invoice is wrong, send it back to the supplier.",
  LINE_ITEMS_MISMATCH: "Check each line amount and the subtotal on the page. Correct any misread number, or query the supplier if the invoice itself is wrong.",
  LINE_ITEM_MATH: "Check quantity, unit price and amount for the line shown in red. Correct a misread number, or query the supplier.",
  INVALID_AMOUNT: "Check the amount on the page and correct it. Negative totals are only valid on credit notes.",
  UNUSUAL_TAX_RATE: "Confirm the tax rate with the supplier's terms before paying.",
  AMBIGUOUS_DATE: "Look at the supplier's other invoices or the due date to decide day and month, then enter the date as YYYY-MM-DD.",
  FUTURE_DATE: "Check the date on the page; correct it if it was misread, otherwise ask the supplier.",
  INVALID_DATE: "Check the date on the page and correct it.",
  LOW_OCR_QUALITY: "Compare every value with the page image. If possible, upload a clearer scan.",
  READ_FROM_IMAGE: "Compare the listed values with the page image. Approve if they are right; edit any that are not.",
  SELF_CHECK_REREAD: "No action needed; the values passed the checks after the second reading.",
  DUPLICATE_INVOICE: "Do not pay twice. Open the earlier copy, confirm it is the same invoice, then reject or delete this one.",
  POSSIBLE_DUPLICATE: "Open both invoices. If they are the same purchase, treat this one as a duplicate.",
  DUPLICATE_FILE: "This exact file was already processed. You can delete this copy.",
  CROSS_CHECK_MISMATCH: "Open Cross-checks to see both documents side by side, find which one is right, and correct the other.",
  LEDGER_MATCH: "No action needed.",
  NOT_AN_INVOICE: "If this page is not an invoice, delete it or ignore it.",
  NO_TEXT_FOUND: "Check that the file is not blank. Upload a clearer copy if needed.",
  NO_INVOICE_DATA: "Add column headers such as Invoice No, Date, Supplier and Total, then upload again.",
  DAMAGED_FILE: "Results may be incomplete. Upload an undamaged copy if you have one.",
  DAMAGED_PAGE: "Check the page in the original file; upload a repaired copy if needed.",
  CORRUPTED_FILE: "Open the file on your computer. If it does not open there either, ask the sender for a new copy.",
  EMPTY_FILE: "The upload was empty. Upload the file again.",
  UNSUPPORTED_TYPE: "Save or export the file as PDF, JPG, PNG, TIFF, XLSX, XLS or CSV and upload it again.",
  PASSWORD_PROTECTED: "Open the PDF with its password, save an unlocked copy, and upload that.",
  TOO_MANY_PAGES: "Split the PDF into smaller files and upload them.",
  EMPTY_DOCUMENT: "The file has no pages or sheets. Check the original.",
  AI_UNAVAILABLE: "Wait a minute, then press Process again (or Retry all failed on the Documents page).",
  JOB_TIMEOUT: "Press Process again. If it keeps happening, split the file into smaller parts.",
  WORKER_ERROR: "Press Process again. The System page shows whether workers are running.",
  WORKER_LOST: "Press Process again. If it fails again, check the System page and the processing history.",
  INTERNAL_ERROR: "Press Process again. If it fails again, open Processing history for the technical details.",
  FILE_TOO_LARGE: "Compress the file or split it into smaller parts.",
};
ACTION.READINGS_DISAGREE = "Look at the page image and decide which reading is right. If the kept value is wrong, press Edit and correct it; then Approve.";
Object.assign(ISSUE, {
  READINGS_DISAGREE: { title: "Two readings differ", explain: "Scans are read twice (OCR text and page image). The two readings gave different values for this field." },
  JOB_TIMEOUT: { title: "Took too long", explain: "Processing went over the time limit and was stopped." },
  WORKER_ERROR: { title: "Worker stopped", explain: "The background worker stopped unexpectedly." },
  WORKER_LOST: { title: "Worker lost", explain: "The worker stopped responding several times while processing this file." },
});
