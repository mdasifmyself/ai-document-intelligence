"use client";
import { FileStack, RotateCcw, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Gate } from "@/components/Gate";
import ExportButton from "@/components/ExportButton";
import { Empty, ErrorNote, Kind, Skeleton, StatusPill, useToast } from "@/components/ui";
import { Doc, getJSON, Paged, postJSON } from "@/lib/api";
import { bytes, duration, fileKind, when } from "@/lib/format";
import { ISSUE, METHOD, STAGE } from "@/lib/labels";

const TABS = [
  ["", "All"], ["queued,processing", "In progress"], ["needs_review", "Needs review"], ["completed", "Done"], ["failed", "Failed"],
] as const;

function Documents() {
  const router = useRouter();
  const toast = useToast();
  const [tab, setTab] = useState<string>("");
  useEffect(() => {  // links like /documents?status=failed open the right tab
    const st = new URLSearchParams(window.location.search).get("status");
    if (st && TABS.some(([k]) => k === st)) setTab(st);
  }, []);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paged<Doc> | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    if (tab) params.set("status", tab);
    if (query) params.set("q", query);
    getJSON<Paged<Doc>>(`/documents?${params}`).then((d) => { setData(d); setError(null); }).catch(setError);
    getJSON<{ documents: { by_status: Record<string, number> } }>("/stats").then((s) => setCounts(s.documents.by_status)).catch(() => {});
  }, [tab, query, page]);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load]);

  const countFor = (key: string) => key ? key.split(",").reduce((n, k) => n + (counts[k] || 0), 0) : Object.values(counts).reduce((a, b) => a + b, 0);

  async function retryFailed() {
    const r = await postJSON<{ requeued: number }>("/jobs/reprocess-failed");
    toast.show(`${r.requeued} failed document${r.requeued === 1 ? "" : "s"} sent back to the queue`);
    load();
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Documents</h1>
          <p>Every uploaded file with its status. Open one to see the page next to the extracted data. <span className="faint">Done = all checks passed · Needs review = a person should look · Failed = could not be read (the reason is shown).</span></p>
        </div>
        <div className="row wrap">
          {tab === "failed" && countFor("failed") > 0 && (
            <button className="btn" onClick={retryFailed}><RotateCcw size={15} /> Retry all failed</button>
          )}
          <ExportButton query={tab ? `status=${tab}` : ""} />
        </div>
      </div>

      <div className="card">
        <div style={{ padding: "14px 18px 0" }}>
          <div className="row between wrap" style={{ gap: 12 }}>
            <div className="tabs" style={{ marginBottom: 0, borderBottom: 0 }}>
              {TABS.map(([key, label]) => (
                <button key={key} className={tab === key ? "on" : ""} onClick={() => { setTab(key); setPage(1); }}>
                  {label}<span className="count num">{countFor(key)}</span>
                </button>
              ))}
            </div>
            <form className="search-box" style={{ maxWidth: 320 }} onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); setPage(1); }}>
              <Search size={16} style={{ left: 12 }} />
              <input className="input" style={{ width: "100%", paddingLeft: 36 }} placeholder="File name or any word inside" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search documents" />
            </form>
          </div>
        </div>
        <div className="divider" style={{ margin: "12px 0 0" }} />
        <ErrorNote error={error} />
        <div className="table-wrap">
          {!data ? <div className="stack" style={{ padding: 20 }}><Skeleton /><Skeleton /><Skeleton /><Skeleton /></div> : data.items.length === 0 ? (
            <Empty icon={<FileStack size={22} />} title={query ? "No documents match" : "No documents here"}>
              {query ? "Try another word, or clear the search." : "Upload files or process the sample set on the Upload page."}
            </Empty>
          ) : (
            <table className="table">
              <thead>
                <tr><th>File</th><th className="hide-sm">Read with</th><th className="r hide-sm">Pages</th><th className="r hide-sm">Invoices</th><th className="r hide-sm">To check</th><th className="r hide-sm">Time</th><th className="hide-sm">Status</th></tr>
              </thead>
              <tbody>
                {data.items.map((d) => (
                  <tr key={d.id} className="click" onClick={() => router.push(`/documents/${d.id}`)}>
                    <td>
                      <div className="row" style={{ minWidth: 0 }}>
                        <Kind>{fileKind(d.filename, d.file_type)}</Kind>
                        <div style={{ minWidth: 0 }}>
                          <span className="fname">{d.filename}</span>
                          <span className="faint small">
                            {when(d.created_at)} · {bytes(d.size_bytes)}
                            {d.status === "processing" && ` · ${STAGE[d.progress?.stage || ""] || "Working"}${d.progress?.total ? ` ${d.progress.done}/${d.progress.total}` : ""}`}
                            {d.status === "failed" && <span style={{ color: "var(--red)" }}> · {ISSUE[d.error_code || ""]?.title || d.error_code}</span>}
                          </span>
                          <span className="show-sm" style={{ marginTop: 6, gap: 8, alignItems: "center" }}><StatusPill status={d.status} /><span className="faint small">{d.invoice_count} invoice{d.invoice_count === 1 ? "" : "s"}</span></span>
                        </div>
                      </div>
                    </td>
                    <td className="hide-sm small muted">{d.text_method ? METHOD[d.text_method] || d.text_method : "—"}{d.ocr_confidence != null && <span className="faint"> · {Math.round(d.ocr_confidence)}%</span>}</td>
                    <td className="r hide-sm num">{d.page_count ?? "—"}</td>
                    <td className="r num hide-sm">{d.invoice_count}</td>
                    <td className="r hide-sm num">{d.issue_count || "—"}</td>
                    <td className="r hide-sm num small muted">{duration(d.processing_ms)}</td>
                    <td className="hide-sm"><StatusPill status={d.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {data && data.total > data.page_size && (
          <div className="row between" style={{ padding: "12px 18px" }}>
            <span className="faint small">{(page - 1) * data.page_size + 1}–{Math.min(page * data.page_size, data.total)} of {data.total}</span>
            <span className="row">
              <button className="btn btn-sm" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
              <button className="btn btn-sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</button>
            </span>
          </div>
        )}
      </div>
      {toast.node}
    </>
  );
}

export default function Page() {
  return <Gate><Documents /></Gate>;
}
