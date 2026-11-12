import { AlertCircle, ArrowRight, BookOpen, Brain, Code2, FileCheck2, FileSearch, Quote, Search, Upload } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/Shell";
import { API_URL, PREPARED_FOR, REPO_URL } from "@/lib/api";

const FLOW = [
  { icon: Upload, title: "Upload", text: "PDFs, scans, photos, TIFF, Excel and CSV. Many at once." },
  { icon: FileSearch, title: "Read", text: "Text layer, OCR with image clean-up, every sheet." },
  { icon: Brain, title: "Extract", text: "AI fills the invoice fields and quotes its source." },
  { icon: FileCheck2, title: "Check", text: "Proof, maths, duplicates and other documents." },
  { icon: Search, title: "Search", text: "By words or by meaning, with filters." },
];

const HANDLES = ["PDFs up to 1,500 pages", "Many invoices in one PDF", "Scans and phone photos", "Multi-page TIFF", "Every Excel sheet", "Old .xls files", "CSV in any number format", "Broken and locked files"];

function Preview() {
  return (
    <div className="card preview-card" style={{ boxShadow: "var(--shadow)" }} aria-label="Example of an extracted invoice">
      <div className="row between">
        <span className="row" style={{ gap: 8 }}><span className="kind">PDF</span><b style={{ fontWeight: 500 }}>INV-20260041</b></span>
        <span className="pill tone-neutral">Sample</span>
      </div>
      {[["Supplier", "Northwind Medical Supplies Ltd", "From: Northwind Medical Supplies Ltd"], ["Invoice date", "14 Mar 2026", "Date: 14 Mar 2026"], ["Subtotal", "1,000.00", "Subtotal 1,000.00"], ["Tax", "150.00", "Tax (15%) 150.00"]].map(([k, v, q]) => (
        <div key={k} className="field-row compact">
          <span className="k">{k}</span>
          <div><span className="v">{v}</span><div className="proof"><Quote size={11} /><q>{q}</q></div></div>
        </div>
      ))}
      <div className="field-row compact">
        <span className="k">Total</span>
        <div><span className="v flag">USD 1,200.00</span><div className="proof"><Quote size={11} /><q>Total Due USD 1,200.00</q></div></div>
      </div>
      <div className="issue error">
        <AlertCircle size={18} strokeWidth={1.9} />
        <div><div className="t">Total does not add up</div><div className="m">Subtotal 1,000.00 + tax 150.00 = 1,150.00, but the total says 1,200.00.</div></div>
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <div className="land">
      <header className="land-nav">
        <Logo />
        <nav className="row" style={{ gap: 4 }}>
          <Link href="/guide" className="btn btn-ghost hide-sm">How to use</Link>
          <Link href="/how-it-works" className="btn btn-ghost hide-sm">How it works</Link>
          <Link href="/dashboard" className="btn btn-dark">Open the app</Link>
        </nav>
      </header>

      <section className="land-hero">
        <div>
          {PREPARED_FOR && <span className="tag-prepared">Prepared for {PREPARED_FOR}</span>}
          <h1 style={{ marginTop: 18 }}>Invoices in.<br /><span className="text-grad">Checked data out.</span></h1>
          <p className="lead">DocIntel reads invoices, receipts, scans, photos, Excel and CSV files, extracts the invoice data with AI, proves every value against the document, checks the numbers, and sends only the unsure cases to a person.</p>
          <div className="row wrap" style={{ marginTop: 28, gap: 10 }}>
            <Link href="/upload" className="btn btn-primary btn-lg">Try it with sample files <ArrowRight size={17} /></Link>
            <Link href="/guide" className="btn btn-lg"><BookOpen size={16} /> How to use</Link>
          </div>
        </div>
        <Preview />
      </section>

      <section className="land-sec">
        <div className="flow">
          {FLOW.map(({ icon: Icon, title, text }) => (
            <div key={title} className="card">
              <span className="ico"><Icon size={18} /></span>
              <h3>{title}</h3>
              <p className="muted small">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="land-sec" style={{ paddingTop: 8 }}>
        <div className="band card-pad row between wrap" style={{ gap: 16, padding: "26px 28px" }}>
          <div style={{ maxWidth: 520 }}>
            <h2>Built for messy, <span className="text-orange">real-world files</span></h2>
            <p className="small" style={{ marginTop: 6 }}>Nothing is guessed: a value without proof stays empty and is flagged for review.</p>
          </div>
          <div className="row wrap" style={{ gap: 8, maxWidth: 560 }}>
            {HANDLES.map((h) => <span key={h} className="pill" style={{ height: 30, padding: "0 12px" }}>{h}</span>)}
          </div>
        </div>
      </section>

      <footer className="land-sec row between wrap faint small" style={{ paddingBottom: 48 }}>
        <span>Built by Md Asif for the Care Guide AI Engineer assessment · sample companies are fictional</span>
        <span className="row" style={{ gap: 16 }}>
          <a href={`${API_URL}/api/docs`} target="_blank" rel="noreferrer" className="row" style={{ gap: 6 }}><Code2 size={14} /> API reference</a>
          {REPO_URL && <a href={REPO_URL} target="_blank" rel="noreferrer">Source code</a>}
        </span>
      </footer>
    </div>
  );
}
