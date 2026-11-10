# How to use DocIntel

Demo: **https://docintel-invoice-ai.vercel.app** (the access code is in the submission email; a link with
`?code=…` fills it in automatically and the code is then stored only in your browser).

## The screens

| Screen | What it is for |
|---|---|
| **Dashboard** | The overview: totals, files being processed, what waits for a person, the problems the checks found, cross-check results and invoice value per currency. The "Start here" guide shows the three steps. |
| **Upload** | Drop files (PDF, JPG, PNG, TIFF, XLSX, XLS, CSV; up to 50 files, 50 MB each). Watch each file's stage live. "Process all sample files" runs 12 prepared test files. |
| **Documents** | Every file with its status. Tabs: In progress, Needs review, Done, Failed. "Retry all failed" re-queues failed files. "Export to Excel" downloads the current tab. |
| **Document detail** | The original page on the left; on the right a one-sentence summary, "Needs your attention" (each problem with **What to do**), every field with its proof quote and confidence, line items, and changes by people. Tabs: Processing history (every stage with its time) and JSON (the API result). |
| **Review queue** | Only invoices that need a person, with the reason. Open, compare with the page, fix, approve. |
| **Search** | Smart (words + meaning), Exact words, or Meaning. Filters: supplier, currency, dates, amounts, review status. "Export filtered" downloads the result as Excel. |
| **Cross-checks** | The same invoice found in two documents (PDF ↔ Excel, PDF ↔ PDF…), compared field by field: Match, Values differ, Duplicate. |
| **System health** | Workers, backlog, AI service state and daily budget, stuck files (recovered automatically), recent failures with what to do, recent automatic recoveries. |
| **How to use / How it works** | Built-in guide and architecture overview (open without the access code). |

## A typical session

1. **Upload.** Open *Upload*, drop files or press *Process all sample files*. Each file shows *Waiting → Checking the
   file → Reading pages → Finding invoices → Extracting with AI → Checking numbers → Looking for duplicates → Making
   it searchable → Done*. When everything is finished, a **Next step** note says what to do.
2. **Check.** Open *Review queue* (the sidebar shows how many are waiting). Open an invoice. Read the summary
   sentence, then the *Needs your attention* box: each problem says what is wrong and **What to do**. Compare with the
   page image on the left (use the arrows for multi-page files).
3. **Fix.** Press *Edit*, correct the value, optionally write a reason, *Save corrections*. All checks run again
   immediately: a fixed total removes the "Total does not add up" problem. Every change is kept in *Changes by people*.
4. **Approve.** Press *Approve* when the invoice is right. It leaves the review queue and counts as reviewed.
5. **Find and export.** Use *Search* (try "medical gloves" in *Meaning* mode) or *Export to Excel* on any list.

## Reading the results

| You see | It means |
|---|---|
| A value with a quote under it | The value was found in the document; the quote is the exact text it came from. |
| "confirmed by two readings" | A scan was read twice (OCR text and page image) and both gave this value. |
| "read from the image" | Only the image reading could read it (poor scan): please confirm. |
| "Removed: no proof in the document (AI suggested …)" | The AI proposed a value it could not prove; it was removed. Check the page and enter it if it is there. |
| "Not on the document" | The field is not printed. It is left empty, never guessed. |
| Confidence bar | How sure the system is (proof found, reading quality). Below 70 % shows amber. |
| Red value | This field has a problem; the reason is in *Needs your attention*. |

## Statuses

| Status | Meaning |
|---|---|
| Waiting | In the queue; a worker starts in a moment. |
| Processing | Being read and checked; the stage is shown live. |
| Done | Read successfully and every check passed. |
| Needs review | Read successfully, but a person should check the flagged items. |
| Failed | The file could not be processed; the reason and what to do are shown. It can be processed again. |
| Approved | A person reviewed and approved the invoice. |

## When something goes wrong

* **A file failed.** Open it: the red box names the problem (damaged, password-protected, empty…) and what to do.
  Temporary problems (AI service unavailable, timeout, worker restart) can be retried with *Process again* or
  *Retry all failed*.
* **"Reconnecting to the processing server…"** The app lost the connection for a moment (for example during an
  update). Nothing is lost; the page retries by itself.
* **A file seems stuck.** *System health* lists files without progress. Files whose worker stopped are put back in
  the queue automatically within a few minutes, and finished AI work is reused.
