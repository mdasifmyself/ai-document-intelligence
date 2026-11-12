import { CheckCheck, FileStack, GitCompareArrows, Search, ShieldCheck, Upload } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { ISSUE, STATUS } from "@/lib/labels";
import { API_URL } from "@/lib/api";

export const metadata: Metadata = { title: "How to use" };

const STEPS = [
  { icon: Upload, title: "Upload your files", href: "/upload", text: "Open Upload and drop one or many files: PDF, JPG, PNG, TIFF, XLSX, XLS or CSV. No files at hand? Press “Process all sample files”." },
  { icon: FileStack, title: "Watch them being processed", href: "/documents", text: "Each file shows its stage live: checking the file, reading pages, finding invoices, extracting with AI, checking numbers. You can leave the page; work continues in the background." },
  { icon: ShieldCheck, title: "Check what needs a person", href: "/review", text: "The Review queue lists invoices where a check failed or a value could not be proven. Open one: the original page is on the left, the extracted data on the right, with the exact quote each value came from." },
  { icon: CheckCheck, title: "Fix and approve", href: "/review", text: "Press Edit to correct a value, add a reason, and save. The checks run again at once. Press Approve when the invoice is right. Every change is kept in the history with who, when and why." },
  { icon: Search, title: "Find anything later", href: "/search", text: "Search by words (invoice numbers, suppliers), by meaning (“medical supplies”), or both. Filter by supplier, currency, date, amount or review status." },
  { icon: GitCompareArrows, title: "See cross-checks", href: "/cross-checks", text: "When the same invoice appears in two documents, such as a PDF and the Excel ledger, the values are compared field by field. Differences and duplicates are flagged." },
];

const GROUPS: [string, string[]][] = [
  ["Numbers", ["TOTAL_MISMATCH", "LINE_ITEMS_MISMATCH", "LINE_ITEM_MATH", "INVALID_AMOUNT", "UNUSUAL_TAX_RATE"]],
  ["Missing or uncertain values", ["MISSING_FIELD", "UNVERIFIED_VALUE", "AMBIGUOUS_DATE", "READ_FROM_IMAGE", "LOW_OCR_QUALITY", "SELF_CHECK_REREAD"]],
  ["Duplicates and other documents", ["DUPLICATE_INVOICE", "POSSIBLE_DUPLICATE", "DUPLICATE_FILE", "CROSS_CHECK_MISMATCH", "LEDGER_MATCH"]],
  ["Files that cannot be processed", ["CORRUPTED_FILE", "PASSWORD_PROTECTED", "EMPTY_FILE", "UNSUPPORTED_TYPE", "TOO_MANY_PAGES", "AI_UNAVAILABLE"]],
];

export default function Guide() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>How to use DocIntel</h1>
          <p>Six steps, from upload to searchable, checked data. Each step links to its page.</p>
        </div>
      </div>

      <div className="grid g-2" style={{ marginBottom: 16 }}>
        {STEPS.map(({ icon: Icon, title, href, text }, i) => (
          <Link key={title} href={href} className="card card-pad step" style={{ alignItems: "start" }}>
            <span className="n">{i + 1}</span>
            <div>
              <h3 className="row" style={{ gap: 8 }}><Icon size={16} strokeWidth={1.75} /> {title}</h3>
              <p className="muted small" style={{ marginTop: 6 }}>{text}</p>
            </div>
          </Link>
        ))}
      </div>

      <div className="grid g-2" style={{ alignItems: "start" }}>
        <div className="card card-pad">
          <h2 style={{ marginBottom: 12 }}>What the statuses mean</h2>
          <div className="kbd-list">
            {["queued", "processing", "completed", "needs_review", "failed", "reviewed"].map((k) => (
              <div key={k} style={{ display: "contents" }}>
                <span className={`pill tone-${STATUS[k].tone}`}><span className="dot" />{STATUS[k].label}</span>
                <span className="muted small">{STATUS[k].hint}</span>
              </div>
            ))}
          </div>
          <div className="divider" />
          <h2 style={{ marginBottom: 10 }}>Files and limits</h2>
          <ul className="prose small" style={{ paddingLeft: 18, margin: 0 }}>
            <li>PDF (text or scanned, up to 1,500 pages), JPG, PNG, TIFF (multi-page), XLSX, XLS, CSV.</li>
            <li>Up to 50 files per upload, 50 MB each.</li>
            <li>A long PDF can hold many invoices; each one is found and extracted separately.</li>
            <li>Every Excel sheet is read. Sheets with columns like Invoice No, Date, Supplier, Total are read row by row.</li>
            <li>The demo needs an access code (in the email that shared this demo). It is kept only until you close the browser; <b>Lock demo</b> in the sidebar locks it at once.</li>
          </ul>
          <div className="divider" />
          <h2 style={{ marginBottom: 10 }}>The one rule the AI follows</h2>
          <p className="muted small">Every value must come with a quote from the document. The system then checks in code that the quote is really there and that the value is inside it. If not, the value is removed and the invoice goes to review. A blank field is always better than a guessed one.</p>
        </div>

        <div className="card card-pad">
          <h2 style={{ marginBottom: 4 }}>What each check means</h2>
          <p className="faint small" style={{ marginBottom: 12 }}>Red items must be fixed or confirmed; amber items deserve a look; blue items are for information.</p>
          {GROUPS.map(([g, codes]) => (
            <div key={g} style={{ marginBottom: 14 }}>
              <h3 style={{ marginBottom: 6 }}>{g}</h3>
              {codes.map((c) => (
                <div key={c} className="small" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                  <b style={{ fontWeight: 500 }}>{ISSUE[c].title}.</b> <span className="muted">{ISSUE[c].explain}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="card card-pad row between wrap" style={{ marginTop: 16, gap: 12 }}>
        <div>
          <h2>For developers</h2>
          <p className="muted small" style={{ marginTop: 4 }}>Everything in this app is available as a REST API with interactive documentation.</p>
        </div>
        <div className="row wrap">
          <a className="btn" href={`${API_URL}/api/docs`} target="_blank" rel="noreferrer">Open the API reference</a>
          <Link className="btn btn-dark" href="/how-it-works">How it works</Link>
        </div>
      </div>
    </>
  );
}
