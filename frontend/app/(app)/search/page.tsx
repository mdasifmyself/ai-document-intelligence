"use client";
import { Search as SearchIcon, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Gate } from "@/components/Gate";
import ExportButton from "@/components/ExportButton";
import { Empty, ErrorNote, Kind, StatusPill } from "@/components/ui";
import { getJSON, SearchHit } from "@/lib/api";
import { dateText, fileKind, money } from "@/lib/format";

const MODES = [
  ["hybrid", "Smart", "Words and meaning together (recommended)"],
  ["keyword", "Exact words", "Finds the words you type, invoice numbers and supplier names"],
  ["semantic", "Meaning", "Finds invoices about the same thing, even with different words"],
] as const;
const EXAMPLES = ["cleaning services", "medical gloves", "office furniture", "IT support", "Northwind"];

interface Result { query: string; mode: string; total: number; took_ms: number; hits: SearchHit[] }

function SearchPage() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<string>("hybrid");
  const [filters, setFilters] = useState({ supplier: "", currency: "", date_from: "", date_to: "", min_total: "", max_total: "", needs_review: "" });
  const [showFilters, setShowFilters] = useState(false);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function run(query = q, m = mode) {
    setBusy(true); setError(null);
    const p = new URLSearchParams({ q: query, mode: m, limit: "30" });
    Object.entries(filters).forEach(([k, v]) => v && p.set(k, v));
    try { setRes(await getJSON<Result>(`/search?${p}`)); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  useEffect(() => { run("", "hybrid"); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const active = Object.values(filters).filter(Boolean).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Search</h1>
          <p>Search every processed invoice by words, by meaning, or both. Add filters to narrow it down.</p>
        </div>
      </div>
      <div className="card card-pad stack" style={{ marginBottom: 16 }}>
        <form className="row wrap" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <div className="search-box" style={{ minWidth: 240 }}>
            <SearchIcon size={18} />
            <input className="input input-lg" placeholder="Try “cleaning services”, a supplier or an invoice number" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
          </div>
          <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Searching…" : "Search"}</button>
        </form>
        <div className="row between wrap" style={{ gap: 10 }}>
          <div className="seg" role="radiogroup" aria-label="Search mode">
            {MODES.map(([k, label, hint]) => (
              <button key={k} type="button" role="radio" aria-checked={mode === k} className={mode === k ? "on" : ""} title={hint} onClick={() => { setMode(k); if (q) run(q, k); }}>{label}</button>
            ))}
          </div>
          <button type="button" className="btn btn-sm" onClick={() => setShowFilters(!showFilters)}><SlidersHorizontal size={14} /> Filters{active ? ` (${active})` : ""}</button>
        </div>
        <p className="faint small">{MODES.find((m) => m[0] === mode)?.[2]}. Examples:{" "}
          {EXAMPLES.map((e, i) => <span key={e}><button type="button" className="btn-ghost" style={{ border: 0, background: "none", color: "var(--blue)", cursor: "pointer", padding: 0 }} onClick={() => { setQ(e); run(e); }}>{e}</button>{i < EXAMPLES.length - 1 ? ", " : ""}</span>)}
        </p>
        {showFilters && (
          <div className="grid g-4" style={{ gap: 10 }}>
            <input className="input" placeholder="Supplier contains" value={filters.supplier} onChange={(e) => setFilters({ ...filters, supplier: e.target.value })} aria-label="Supplier" />
            <select className="select" value={filters.currency} onChange={(e) => setFilters({ ...filters, currency: e.target.value })} aria-label="Currency">
              <option value="">Any currency</option>{["USD", "EUR", "GBP", "BDT"].map((c) => <option key={c}>{c}</option>)}
            </select>
            <input className="input" type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} aria-label="From date" />
            <input className="input" type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} aria-label="To date" />
            <input className="input" inputMode="decimal" placeholder="Total at least" value={filters.min_total} onChange={(e) => setFilters({ ...filters, min_total: e.target.value })} aria-label="Minimum total" />
            <input className="input" inputMode="decimal" placeholder="Total at most" value={filters.max_total} onChange={(e) => setFilters({ ...filters, max_total: e.target.value })} aria-label="Maximum total" />
            <select className="select" value={filters.needs_review} onChange={(e) => setFilters({ ...filters, needs_review: e.target.value })} aria-label="Review status">
              <option value="">Reviewed or not</option><option value="true">Needs review</option><option value="false">Checked / approved</option>
            </select>
            <div className="row"><button type="button" className="btn" onClick={() => run()}>Apply</button>
              <button type="button" className="btn btn-ghost" onClick={() => setFilters({ supplier: "", currency: "", date_from: "", date_to: "", min_total: "", max_total: "", needs_review: "" })}>Clear</button></div>
          </div>
        )}
      </div>
      <ErrorNote error={error} />
      {res && (
        <div className="card">
          <div className="card-head" style={{ paddingBottom: 6 }}>
            <h2>{res.query ? `${res.total} result${res.total === 1 ? "" : "s"}` : "Latest invoices"}</h2>
            <span className="row" style={{ gap: 10 }}>
              <span className="faint small num">{res.took_ms} ms</span>
              <ExportButton small label="Export filtered" query={new URLSearchParams(Object.entries(filters).filter(([k, v]) => v && ["supplier", "currency", "date_from", "date_to", "needs_review"].includes(k))).toString()} />
            </span>
          </div>
          {res.hits.length === 0 ? (
            <Empty icon={<SearchIcon size={22} />} title="No matches">Try fewer words, the Meaning mode, or remove a filter.</Empty>
          ) : (
            <div style={{ padding: "6px 10px 10px" }}>
              {res.hits.map((h) => (
                <Link key={h.invoice.id} href={`/documents/${h.invoice.document_id}?invoice=${h.invoice.id}`} className="click" style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, padding: "12px", borderBottom: "1px solid var(--line)", borderRadius: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="row wrap" style={{ gap: 8 }}>
                      <b style={{ fontWeight: 500 }}>{h.invoice.invoice_number || "No number"}</b>
                      <span className="muted">{h.invoice.supplier_name}</span>
                      {res.query && <span className={`pill ${h.match === "semantic" ? "tone-blue" : h.match === "hybrid" ? "tone-cyan" : ""}`}>{h.match === "semantic" ? "Similar meaning" : h.match === "hybrid" ? "Words + meaning" : "Exact words"}</span>}
                    </div>
                    <div className="small faint" style={{ marginTop: 3 }}>
                      {h.snippet ? <span dangerouslySetInnerHTML={{ __html: h.snippet.replace(/<(?!\/?mark>)[^>]*>/g, "") }} /> : (h.invoice.line_items || []).slice(0, 3).map((l) => l.description).join(" · ")}
                    </div>
                    <div className="row small faint" style={{ marginTop: 4, gap: 8 }}><Kind>{fileKind(h.document_filename, h.document_file_type)}</Kind><span className="fname" style={{ maxWidth: 260 }}>{h.document_filename}</span></div>
                  </div>
                  <div style={{ textAlign: "right" }} className="stack">
                    <span className="num" style={{ fontWeight: 500 }}>{money(h.invoice.total, h.invoice.currency)}</span>
                    <span className="faint small">{dateText(h.invoice.invoice_date)}</span>
                    <span><StatusPill status={h.invoice.status} /></span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function Page() {
  return <Gate><SearchPage /></Gate>;
}
