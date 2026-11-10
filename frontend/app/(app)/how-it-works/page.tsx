import { Brain, Database, FileCheck2, FileScan, FileSearch, Gauge, Layers, Lock, Search, ServerCog, ShieldCheck, Split, Workflow } from "lucide-react";
import type { Metadata } from "next";
import evalSummary from "@/lib/eval-summary.json";

export const metadata: Metadata = { title: "How it works" };

const PIPELINE = [
  { icon: FileScan, title: "Check the file", text: "The real type is read from the file's first bytes. Renamed, empty, damaged and locked files are stopped with a clear reason." },
  { icon: FileSearch, title: "Read every page", text: "Text PDFs are read directly. Scans and photos are straightened, cleaned and read with OCR. Every Excel sheet is read." },
  { icon: Split, title: "Find each invoice", text: "A 1,000-page PDF is split into separate invoices by their numbers and page markers like “Page 2 of 3”." },
  { icon: Brain, title: "Extract with AI", text: "A language model fills a fixed JSON form and must quote where each value came from. Hard-to-read pages are read from the image." },
  { icon: FileCheck2, title: "Prove and check", text: "Code checks every quote is really in the document; unproven values are removed. Then totals, tax, line items, dates, duplicates and other documents are checked." },
  { icon: Search, title: "Make it searchable", text: "Results go into PostgreSQL with full-text search and meaning vectors (pgvector), so staff can search by words or by meaning." },
];

const STACK = [
  { icon: Layers, name: "Web app", tech: "Next.js on Vercel", why: "Fast, simple screens for upload, review and search." },
  { icon: ServerCog, name: "API", tech: "Python · FastAPI", why: "The best OCR and spreadsheet tools are in Python; FastAPI writes the interactive API documentation itself." },
  { icon: Workflow, name: "Background work", tech: "Redis · RQ workers", why: "Slow OCR and AI work never blocks the website. Add workers to process more files at once." },
  { icon: FileScan, name: "Reading", tech: "Tesseract OCR · OpenCV · pypdfium2 · pandas", why: "Free, local OCR with image clean-up; exact text from digital PDFs; every Excel sheet." },
  { icon: Brain, name: "AI", tech: "OpenAI models through an n8n gateway", why: "Strict JSON output. The API key stays inside n8n; the gateway allows only two kinds of calls." },
  { icon: Database, name: "Data and search", tech: "PostgreSQL · pgvector", why: "One database for records, history, keyword search and meaning search: fewer moving parts." },
];

const SECURITY = [
  "Access code on every request; HTTPS everywhere.",
  "File type checked from content, size and page limits, rate limits per address.",
  "Containers run as a normal user with CPU and memory limits, on a private network.",
  "The AI key is never in the app; document text is not stored by the AI provider (store: false).",
  "Every manual change is logged: old value, new value, who, when, why.",
];

type Summary = { run_at?: string; field_accuracy?: number; success_rate?: number; broken_handled?: number; planted_caught?: string; doc_ms_p50?: number; big_pages?: number; big_minutes?: number; big_invoices?: number; nulls_kept?: number } | null;

export default function HowItWorks() {
  const s = evalSummary as Summary;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>How it works</h1>
          <p>From a file in the inbox to checked, searchable data, in six automatic steps. A person only looks at what the system is unsure about.</p>
        </div>
      </div>

      <div className="flow" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: 16 }}>
        {PIPELINE.map(({ icon: Icon, title, text }, i) => (
          <div key={title} className="card">
            <div className="row between"><span className="ico"><Icon size={18} /></span><span className="faint small num">Step {i + 1}</span></div>
            <h3>{title}</h3>
            <p className="muted small">{text}</p>
          </div>
        ))}
      </div>

      {s && (
        <div className="card card-pad" style={{ marginBottom: 16 }}>
          <div className="row between wrap" style={{ marginBottom: 14 }}>
            <h2 className="row" style={{ gap: 8 }}><Gauge size={18} /> Measured on a labelled test set</h2>
            <span className="faint small">Run {s.run_at?.slice(0, 10)} · full report in the repository</span>
          </div>
          <div className="grid g-4">
            {s.field_accuracy != null && <div className="stat" style={{ padding: 0 }}><span className="label">Field accuracy</span><span className="value">{s.field_accuracy}%</span><span className="sub">every field compared with the answer key</span></div>}
            {s.success_rate != null && <div className="stat" style={{ padding: 0 }}><span className="label">Documents processed</span><span className="value">{s.success_rate}%</span><span className="sub">of valid files; {s.broken_handled}% of broken files stopped cleanly</span></div>}
            {s.planted_caught && <div className="stat" style={{ padding: 0 }}><span className="label">Planted problems caught</span><span className="value">{s.planted_caught}</span><span className="sub">wrong totals, duplicates, missing values…</span></div>}
            {s.big_pages ? <div className="stat" style={{ padding: 0 }}><span className="label">1,000-page batch</span><span className="value">{s.big_minutes} min</span><span className="sub">{s.big_pages} pages, {s.big_invoices} invoices, on a small 2-CPU server</span></div>
              : s.doc_ms_p50 != null && <div className="stat" style={{ padding: 0 }}><span className="label">Median time per file</span><span className="value">{(s.doc_ms_p50 / 1000).toFixed(1)} s</span><span className="sub">including OCR and AI</span></div>}
          </div>
        </div>
      )}

      <div className="grid g-2" style={{ alignItems: "start" }}>
        <div className="card card-pad">
          <h2 style={{ marginBottom: 12 }}>What it is built with, and why</h2>
          {STACK.map(({ icon: Icon, name, tech, why }) => (
            <div key={name} className="row" style={{ alignItems: "flex-start", padding: "10px 0", borderBottom: "1px solid var(--line)", gap: 12 }}>
              <span className="stat"><span className="ico" style={{ width: 32, height: 32 }}><Icon size={16} /></span></span>
              <div><b style={{ fontWeight: 500 }}>{name}</b> <span className="faint small">· {tech}</span><p className="muted small" style={{ marginTop: 2 }}>{why}</p></div>
            </div>
          ))}
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card card-pad">
            <h2 className="row" style={{ gap: 8, marginBottom: 10 }}><ShieldCheck size={18} /> No made-up values</h2>
            <p className="muted small">Language models can sound sure while being wrong. So the model is never trusted on its own: it must quote the document, and plain code checks the quote and the value. Maths is done by code, never by the model. A missing value stays empty and is flagged.</p>
          </div>
          <div className="card card-pad">
            <h2 className="row" style={{ gap: 8, marginBottom: 10 }}><Lock size={18} /> Security</h2>
            <ul className="prose small" style={{ paddingLeft: 18, margin: 0 }}>{SECURITY.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          <div className="card card-pad">
            <h2 className="row" style={{ gap: 8, marginBottom: 10 }}><Workflow size={18} /> Scaling up</h2>
            <p className="muted small">Each part scales on its own: more workers for more files, more API copies behind the load balancer, a managed PostgreSQL for more data, object storage for originals. The queue absorbs bursts, failed jobs can be retried in one click, and every stage is timed in the processing history.</p>
          </div>
        </div>
      </div>
    </>
  );
}
