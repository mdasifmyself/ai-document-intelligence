"use client";
import { CheckCircle2, CloudUpload, Download, FileWarning, Play, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Gate } from "@/components/Gate";
import { ErrorNote, Kind, StatusPill } from "@/components/ui";
import { Doc, getJSON, Meta, Paged, postJSON, uploadFiles, UploadResponse } from "@/lib/api";
import { bytes, duration, fileKind } from "@/lib/format";
import { ISSUE, STAGE } from "@/lib/labels";

const SAMPLES = [
  ["digital-invoice.pdf", "Normal PDF invoice"], ["scanned-invoice.pdf", "Scanned PDF (OCR)"],
  ["phone-photo.jpg", "Phone photo"], ["blurry-photo.jpg", "Very poor photo (AI vision)"],
  ["two-invoices.tiff", "Multi-page TIFF, 2 invoices"], ["batch-six-invoices.pdf", "One PDF, 6 invoices"],
  ["wrong-total.pdf", "Total does not add up"], ["ledger-q1-2026.xlsx", "Excel ledger, 3 sheets"],
  ["vendors-legacy.xls", "Old Excel (.xls)"], ["export-eu.csv", "CSV, European number format"],
  ["damaged.pdf", "Broken file"], ["locked.pdf", "Password-protected PDF"],
];

function UploadPage() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [picked, setPicked] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [error, setError] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { getJSON<Meta>("/meta").then(setMeta).catch(() => {}); }, []);

  const ids = result?.accepted.map((d) => d.id) || [];
  const idKey = ids.join(",");
  const poll = useCallback(() => {
    if (!idKey) return;
    getJSON<Paged<Doc>>(`/documents?ids=${idKey}&page_size=100`).then((r) => {
      const order = new Map(idKey.split(",").map((id, i) => [id, i]));
      setDocs([...r.items].sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0)));
    }).catch(() => {});
  }, [idKey]);
  useEffect(() => {
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, [poll]);
  const allDone = docs.length > 0 && docs.every((d) => !["queued", "processing"].includes(d.status));
  useEffect(() => { if (allDone) window.dispatchEvent(new Event("docintel-refresh")); }, [allDone]);

  const accept = meta?.allowed_extensions.join(",") || ".pdf,.jpg,.jpeg,.png,.tif,.tiff,.xlsx,.xls,.csv";
  const add = (list: FileList | null) => {
    if (!list) return;
    setPicked((p) => [...p, ...Array.from(list)].slice(0, meta?.max_files_per_upload || 50));
  };

  async function send(files: File[]) {
    setError(null); setResult(null); setDocs([]); setProgress(0);
    try {
      const r = await uploadFiles(files, setProgress);
      setResult(r); setPicked([]);
    } catch (e) { setError(e); } finally { setProgress(null); }
  }

  async function samples() {
    setError(null); setResult(null); setDocs([]); setProgress(100);
    try { setResult(await postJSON<UploadResponse>("/samples/load")); } catch (e) { setError(e); } finally { setProgress(null); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Upload files</h1>
          <p>Drop invoices, receipts, scans, photos or spreadsheets. They are processed in the background, so you can leave this page at any time.</p>
        </div>
      </div>

      <div className="split">
        <div className="stack" style={{ gap: 16 }}>
          <div
            className={`drop ${over ? "over" : ""}`}
            role="button" tabIndex={0}
            onClick={() => input.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}
          >
            <div className="big-ico"><CloudUpload size={26} /></div>
            <h2>Drop files here, or click to choose</h2>
            <p className="muted small">PDF, JPG, PNG, TIFF, XLSX, XLS or CSV · up to {meta?.max_files_per_upload ?? 50} files · {meta?.max_file_mb ?? 50} MB each · up to {meta?.max_pages ?? 1500} pages per file</p>
            <input ref={input} type="file" multiple accept={accept} hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          </div>

          {picked.length > 0 && (
            <div className="card">
              <div className="card-head"><h2>{picked.length} file{picked.length > 1 ? "s" : ""} ready</h2>
                <button className="btn btn-sm btn-ghost" onClick={() => setPicked([])}>Clear</button></div>
              <div style={{ padding: "8px 14px 4px" }}>
                {picked.map((f, i) => (
                  <div key={i} className="row between" style={{ padding: "8px", borderBottom: "1px solid var(--line)" }}>
                    <span className="row" style={{ minWidth: 0 }}><Kind>{fileKind(f.name)}</Kind><span className="fname" style={{ maxWidth: 300 }}>{f.name}</span></span>
                    <span className="row"><span className="faint small">{bytes(f.size)}</span>
                      <button className="btn icon-btn btn-ghost btn-sm" aria-label={`Remove ${f.name}`} onClick={() => setPicked((p) => p.filter((_, j) => j !== i))}><X size={15} /></button></span>
                  </div>
                ))}
              </div>
              <div style={{ padding: 16 }}>
                <button className="btn btn-primary btn-lg" style={{ width: "100%" }} disabled={progress !== null} onClick={() => send(picked)}>
                  {progress !== null ? `Uploading… ${progress}%` : `Upload and process ${picked.length} file${picked.length > 1 ? "s" : ""}`}
                </button>
                {progress !== null && <div className="bar" style={{ marginTop: 10 }}><span style={{ width: `${progress}%` }} /></div>}
              </div>
            </div>
          )}
          <ErrorNote error={error} />

          {result && (
            <div className="card">
              <div className="card-head">
                <h2>{allDone ? "Finished" : "Processing…"}</h2>
                {allDone && <Link href="/documents" className="btn btn-sm">Open documents</Link>}
              </div>
              {allDone && (() => {
                const review = docs.filter((d) => d.status === "needs_review").length;
                const failedN = docs.filter((d) => d.status === "failed").length;
                return (
                  <div className={`notice ${review || failedN ? "warn" : ""}`} style={{ margin: "12px 14px 0" }}>
                    <span>
                      <b style={{ fontWeight: 600 }}>Next step: </b>
                      {review ? <>{review} file{review === 1 ? " has" : "s have"} something to check. <Link href="/review" style={{ textDecoration: "underline" }}>Open the review queue</Link>.</> : "Everything passed its checks. "}
                      {failedN ? <> {failedN} file{failedN === 1 ? "" : "s"} could not be read; open {failedN === 1 ? "it" : "them"} below to see why and what to do.</> : null}
                      {!review && !failedN && <Link href="/search" style={{ textDecoration: "underline" }}>Search or export the results</Link>}
                    </span>
                  </div>
                );
              })()}
              <div style={{ padding: "8px 14px 14px" }}>
                {result.rejected.map((r) => (
                  <div key={r.filename} className="row between" style={{ padding: "10px 8px", borderBottom: "1px solid var(--line)" }}>
                    <span className="row" style={{ minWidth: 0 }}><FileWarning size={16} color="var(--red)" /><span className="fname" style={{ maxWidth: 260 }}>{r.filename}</span></span>
                    <span className="small" style={{ color: "var(--red)" }}>{r.message}</span>
                  </div>
                ))}
                {(docs.length ? docs : result.accepted).map((d) => {
                  const p = d.progress || {};
                  const pct = d.status === "processing" && p.total ? Math.round(((p.done || 0) / p.total) * 100) : null;
                  return (
                    <Link key={d.id} href={`/documents/${d.id}`} className="click" style={{ display: "block", padding: "10px 8px", borderBottom: "1px solid var(--line)" }}>
                      <div className="row between">
                        <span className="row" style={{ minWidth: 0 }}><Kind>{fileKind(d.filename, d.file_type)}</Kind><span className="fname" style={{ maxWidth: 240 }}>{d.filename}</span></span>
                        <StatusPill status={d.status} />
                      </div>
                      <div className="faint small" style={{ marginTop: 4, paddingLeft: 2 }}>
                        {d.status === "processing" && <>{STAGE[p.stage || ""] || "Working"}{p.total ? ` · ${p.done}/${p.total}` : ""}</>}
                        {d.status === "queued" && "Waiting for a free worker"}
                        {["completed", "needs_review"].includes(d.status) && `${d.invoice_count} invoice${d.invoice_count === 1 ? "" : "s"} · ${d.issue_count} item${d.issue_count === 1 ? "" : "s"} to check · ${duration(d.processing_ms)}`}
                        {d.status === "failed" && <span style={{ color: "var(--red)" }}>{ISSUE[d.error_code || ""]?.title || d.error_code}: {d.error_message}</span>}
                      </div>
                      {pct !== null && <div className="bar" style={{ marginTop: 6 }}><span style={{ width: `${pct}%` }} /></div>}
                    </Link>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="stack" style={{ gap: 16 }}>
          <div className="card card-pad stack">
            <h2 style={{ fontSize: 17 }}>No files at hand? Try the samples</h2>
            <p className="muted small">Twelve test files built for this demo, from a clean PDF to a blurry phone photo, a 3-sheet Excel ledger and a broken file. All companies are fictional.</p>
            <button className="btn btn-dark" onClick={samples} disabled={progress !== null}><Play size={15} /> Process all sample files</button>
            <div className="divider" style={{ margin: "4px 0" }} />
            <p className="faint small">Or download one and upload it yourself:</p>
            <div className="stack" style={{ gap: 2 }}>
              {SAMPLES.map(([f, label]) => (
                <a key={f} href={`/samples/${f}`} download className="row between small" style={{ padding: "7px 4px", borderBottom: "1px solid var(--line)" }}>
                  <span className="row" style={{ gap: 8 }}><Kind>{fileKind(f)}</Kind>{label}</span>
                  <Download size={14} color="var(--text-3)" />
                </a>
              ))}
            </div>
          </div>
          <div className="card card-pad stack">
            <h2 style={{ fontSize: 17 }}>What happens next</h2>
            {[["Checked", "The real file type is checked from its content, not its name."], ["Read", "Text PDFs are read directly. Scans and photos go through OCR. Every Excel sheet is read."],
              ["Extracted", "AI finds the invoice fields and must quote where each value came from. No quote, no value."],
              ["Verified", "Totals, tax, line items, duplicates and other documents are checked automatically."]].map(([t, d]) => (
              <div key={t} className="row" style={{ alignItems: "flex-start" }}><CheckCircle2 size={17} color="var(--cyan-600)" style={{ marginTop: 2, flex: "none" }} /><span className="small"><b style={{ fontWeight: 500 }}>{t}.</b> <span className="muted">{d}</span></span></div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

export default function Page() {
  return <Gate><UploadPage /></Gate>;
}
