"use client";
import { ArrowLeft, Download, RotateCcw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import DocViewer from "@/components/DocViewer";
import { Gate } from "@/components/Gate";
import ExportButton from "@/components/ExportButton";
import InvoicePanel from "@/components/InvoicePanel";
import { ErrorNote, Issues, Kind, Skeleton, StatusPill, useToast } from "@/components/ui";
import { blobUrl, del, DocDetail, getJSON, Invoice, postJSON } from "@/lib/api";
import { bytes, duration, fileKind, money, when } from "@/lib/format";
import { ACTION, ISSUE, METHOD, STAGE } from "@/lib/labels";

function Detail() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const toast = useToast();
  const [doc, setDoc] = useState<DocDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [active, setActive] = useState<string | null>(search.get("invoice"));
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState<"data" | "history" | "json">("data");
  const [invFilter, setInvFilter] = useState("");

  const load = useCallback(() => {
    getJSON<DocDetail>(`/documents/${id}`).then((d) => { setDoc(d); setError(null); }).catch(setError);
  }, [id]);
  useEffect(() => { load(); }, [load]);
  const running = doc && ["queued", "processing"].includes(doc.status);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [running, load]);

  const invoices = doc?.invoices || [];
  const current = invoices.find((i) => i.id === active) || invoices[0];
  useEffect(() => {
    if (current?.location?.pages?.length) setPage(current.location.pages[0]);
    else if (current?.location?.sheet && doc) {
      const p = doc.pages.find((x) => x.label === current.location.sheet);
      if (p) setPage(p.page_no);
    }
  }, [current?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function replaceInvoice(updated: Invoice) {
    if (!doc) return;
    setDoc({ ...doc, invoices: doc.invoices.map((i) => (i.id === updated.id ? { ...i, ...updated } : i)) });
    load();
  }

  async function reprocess() {
    if (!doc) return;
    if (!confirm("Process this document again? Its current results and manual corrections will be replaced.")) return;
    await postJSON(`/documents/${doc.id}/reprocess`);
    toast.show("Sent back to the queue");
    load();
  }

  async function remove() {
    if (!doc || !confirm(`Delete “${doc.filename}” and all its results? This cannot be undone.`)) return;
    await del(`/documents/${doc.id}`);
    router.push("/documents");
  }

  async function download() {
    if (!doc) return;
    const url = await blobUrl(`/documents/${doc.id}/file`);
    const a = document.createElement("a");
    a.href = url; a.download = doc.filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  if (error) return <ErrorNote error={error} />;
  if (!doc) return <div className="stack"><Skeleton h={36} w={320} /><Skeleton h={420} /></div>;

  const many = invoices.length > 8;
  const shown = invFilter ? invoices.filter((i) => `${i.invoice_number} ${i.supplier_name}`.toLowerCase().includes(invFilter.toLowerCase())) : invoices;

  return (
    <>
      <Link href="/documents" className="btn btn-sm btn-ghost" style={{ marginLeft: -10, marginBottom: 8 }}><ArrowLeft size={15} /> Documents</Link>
      <div className="page-head" style={{ alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <div className="row" style={{ marginBottom: 6 }}><Kind>{fileKind(doc.filename, doc.file_type)}</Kind><StatusPill status={doc.status} /></div>
          <h1 style={{ overflowWrap: "anywhere" }}>{doc.filename}</h1>
          <p className="small meta-line">
            {[bytes(doc.size_bytes), doc.page_count != null ? `${doc.page_count} ${doc.file_type && ["xlsx", "xls", "csv"].includes(doc.file_type) ? "sheet" : "page"}${doc.page_count === 1 ? "" : "s"}` : null,
              doc.text_method ? `read with ${METHOD[doc.text_method] || doc.text_method}` : null,
              doc.ocr_confidence != null ? `OCR confidence ${Math.round(doc.ocr_confidence)}%` : null,
              doc.processing_ms != null ? `processed in ${duration(doc.processing_ms)}` : null, `uploaded ${when(doc.created_at)}`]
              .filter(Boolean).map((t) => <span key={t as string}>{t}</span>)}
          </p>
        </div>
        <div className="row wrap">
          <button className="btn btn-sm" onClick={download}><Download size={14} /> Original</button>
          {invoices.length > 0 && <ExportButton small query={`document_id=${doc.id}`} label="Excel" />}
          <button className="btn btn-sm" onClick={reprocess} disabled={!!running}><RotateCcw size={14} /> Process again</button>
          <button className="btn btn-sm btn-danger" onClick={remove}><Trash2 size={14} /> Delete</button>
        </div>
      </div>

      {running && (
        <div className="notice" style={{ marginBottom: 16 }}>
          <span className="spinner" style={{ marginTop: 2 }} />
          <span>{STAGE[doc.progress?.stage || ""] || "Working"}{doc.progress?.total ? ` · ${doc.progress.done} of ${doc.progress.total}` : ""}. Results appear here when it finishes.</span>
        </div>
      )}
      {doc.status === "failed" && (
        <div className="notice err" style={{ marginBottom: 16 }}>
          <span>
            <b style={{ fontWeight: 600 }}>{ISSUE[doc.error_code || ""]?.title || doc.error_code}.</b> {doc.error_message}
            {ACTION[doc.error_code || ""] && <><br /><b style={{ fontWeight: 600 }}>What to do:</b> {ACTION[doc.error_code || ""]}</>}
          </span>
        </div>
      )}

      <div className="tabs">
        <button className={tab === "data" ? "on" : ""} onClick={() => setTab("data")}>Extracted data<span className="count">{invoices.length}</span></button>
        <button className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>Processing history</button>
        <button className={tab === "json" ? "on" : ""} onClick={() => setTab("json")}>JSON</button>
      </div>

      {tab === "data" && (
        <div className="split">
          <DocViewer doc={doc} page={page} onPage={setPage} />
          <div className="stack" style={{ gap: 16, minWidth: 0 }}>
            {doc.issues.filter((i) => i.code !== doc.error_code).length > 0 && (
              <div className="card card-pad"><h2 style={{ fontSize: 15, marginBottom: 10 }}>About this file</h2><Issues issues={doc.issues.filter((i) => i.code !== doc.error_code)} /></div>
            )}
            {invoices.length > 1 && (
              <div className="card" style={{ padding: 12 }}>
                <div className="row between" style={{ padding: "2px 6px 8px" }}>
                  <span className="small muted">{invoices.length} invoices in this file · {invoices.filter((i) => i.needs_review).length} need review</span>
                  {many && <input className="input" style={{ height: 32, width: 180 }} placeholder="Find invoice" value={invFilter} onChange={(e) => setInvFilter(e.target.value)} aria-label="Find invoice" />}
                </div>
                <div style={{ maxHeight: many ? 260 : undefined, overflowY: many ? "auto" : undefined }} className="stack">
                  {shown.slice(0, 300).map((i) => (
                    <button key={i.id} onClick={() => setActive(i.id)} className="mini-row" style={{ border: current?.id === i.id ? "1.5px solid var(--cyan)" : "1.5px solid transparent", cursor: "pointer", textAlign: "left", background: current?.id === i.id ? "var(--cyan-50)" : undefined, gap: 8 }}>
                      <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <b style={{ fontWeight: 500 }}>{i.invoice_number || "No number"}</b> <span className="faint small">{i.supplier_name}</span>
                      </span>
                      <span className="row" style={{ gap: 8 }}><span className="num small">{money(i.total, i.currency)}</span><StatusPill status={i.status} /></span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {current ? <InvoicePanel key={current.id} inv={current} onChange={replaceInvoice} toast={toast.show} /> : !running && doc.status !== "failed" && (
              <div className="card card-pad muted">No invoice data was found in this file.</div>
            )}
          </div>
        </div>
      )}

      {tab === "history" && (
        <div className="card card-pad">
          <div className="timeline">
            {doc.events.map((e) => (
              <div key={e.id} className={`tl ${e.status}`}>
                <span className="d" />
                <div>
                  <div style={{ fontWeight: 500 }} className="small">{STAGE[e.stage] || e.stage} <span className="faint">· {e.status}</span></div>
                  {e.message && <div className="small muted" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{e.message.split("\n")[0]}</div>}
                </div>
                <span className="when num">{e.duration_ms != null ? duration(e.duration_ms) + " · " : ""}{new Date(e.created_at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
          <p className="faint small" style={{ marginTop: 12 }}>Attempts: {doc.attempts} · AI calls: {doc.ai_calls} · File fingerprint (SHA-256): <span className="mono">{doc.sha256.slice(0, 16)}…</span></p>
        </div>
      )}

      {tab === "json" && (
        <div className="card card-pad">
          <p className="small muted" style={{ marginBottom: 10 }}>The structured result, exactly as the API returns it (<span className="mono">GET /api/v1/documents/{doc.id.slice(0, 8)}…</span>).</p>
          <pre className="sheet-text" style={{ maxHeight: "70vh", whiteSpace: "pre-wrap" }}>
            {JSON.stringify(doc.invoices.map(({ issues, corrections, fields, ...rest }) => ({ ...rest, issues: issues?.map((i) => ({ code: i.code, severity: i.severity, field: i.field, message: i.message })) })), null, 2)}
          </pre>
        </div>
      )}
      {toast.node}
    </>
  );
}

export default function Page() {
  return <Gate><Suspense fallback={null}><Detail /></Suspense></Gate>;
}
