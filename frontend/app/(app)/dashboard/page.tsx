"use client";
import { ArrowRight, CheckCircle2, Clock3, FileStack, FileText, Search, ShieldCheck, Upload, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Gate } from "@/components/Gate";
import ExportButton from "@/components/ExportButton";
import { Empty, ErrorNote, Kind, Skeleton, StatusPill } from "@/components/ui";
import { Doc, getJSON, Invoice, Paged, Stats } from "@/lib/api";
import { duration, fileKind, money, when } from "@/lib/format";
import { issueTitle } from "@/lib/labels";

function Dashboard() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [review, setReview] = useState<(Invoice & { document_filename?: string })[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    Promise.all([
      getJSON<Stats>("/stats"),
      getJSON<Paged<Doc>>("/documents?page_size=8"),
      getJSON<Paged<Invoice & { document_filename?: string }>>("/invoices?needs_review=true&page_size=6"),
    ]).then(([s, d, r]) => { setStats(s); setDocs(d.items); setReview(r.items); setError(null); }).catch(setError);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  const [showStart, setShowStart] = useState(true);
  useEffect(() => { try { setShowStart(localStorage.getItem("docintel.hideStart") !== "1"); } catch { /* ignore */ } }, []);
  const hideStart = () => { setShowStart(false); try { localStorage.setItem("docintel.hideStart", "1"); } catch { /* ignore */ } };
  const failed = stats?.documents.by_status.failed || 0;
  const busy = stats ? stats.processing.processing_now + Math.max(0, stats.processing.waiting_in_queue) : 0;
  const byCode = new Map<string, { code: string; severity: string; count: number }>();
  (stats?.issues || []).filter((i) => i.severity !== "info").forEach((i) => {
    const e = byCode.get(i.code) || { code: i.code, severity: i.severity, count: 0 };
    e.count += i.count;
    if (i.severity === "error") e.severity = "error";
    byCode.set(i.code, e);
  });
  const errorsOnly = [...byCode.values()].sort((a, b) => b.count - a.count).slice(0, 7);
  const maxIssue = Math.max(1, ...errorsOnly.map((i) => i.count));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>Everything that was uploaded, what the system found, and what still needs a person.</p>
        </div>
        <div className="row wrap">
          <ExportButton label="Export all" />
          <Link href="/upload" className="btn btn-primary btn-lg"><Upload size={17} /> Upload files</Link>
        </div>
      </div>
      <ErrorNote error={error} />

      {showStart && (
        <div className="card start-card" style={{ marginBottom: 16 }}>
          <div className="row between" style={{ alignItems: "flex-start" }}>
            <div>
              <h2>Start here</h2>
              <p className="muted small" style={{ marginTop: 4 }}>DocIntel reads invoices for you. You only check what it is unsure about. Three steps:</p>
            </div>
            <button className="btn icon-btn btn-ghost btn-sm" aria-label="Hide this guide" title="Hide this guide" onClick={hideStart}><X size={16} /></button>
          </div>
          <div className="start-steps">
            <Link href="/upload" className="start-step"><span className="n">1</span><span><b>Upload files</b><span className="muted small">PDFs, scans, photos, Excel or CSV, or try the sample files.</span></span><Upload size={18} /></Link>
            <Link href="/review" className="start-step"><span className="n">2</span><span><b>Check flagged invoices</b><span className="muted small">See the page next to the data, fix what is wrong, approve.</span></span><ShieldCheck size={18} /></Link>
            <Link href="/search" className="start-step"><span className="n">3</span><span><b>Find and export</b><span className="muted small">Search by words or meaning, download everything to Excel.</span></span><Search size={18} /></Link>
          </div>
        </div>
      )}

      <div className="grid g-4" style={{ marginBottom: 16 }}>
        <div className="card stat">
          <span className="label"><span className="ico"><FileStack size={15} /></span>Documents</span>
          <span className="value">{stats ? stats.documents.total.toLocaleString() : <Skeleton h={32} w={80} />}</span>
          <span className="sub">{stats ? `${stats.documents.pages.toLocaleString()} pages read` : ""}</span>
        </div>
        <div className="card stat">
          <span className="label"><span className="ico"><FileText size={15} /></span>Invoices extracted</span>
          <span className="value">{stats ? stats.invoices.total.toLocaleString() : <Skeleton h={32} w={80} />}</span>
          <span className="sub">{stats ? `${stats.invoices.reviewed} approved by a person` : ""}</span>
        </div>
        <Link href="/review" className="card stat" style={{ background: stats?.invoices.needs_review ? "var(--amber-50)" : undefined }}>
          <span className="label"><span className="ico"><ShieldCheck size={15} /></span>Need review</span>
          <span className="value">{stats ? stats.invoices.needs_review.toLocaleString() : <Skeleton h={32} w={60} />}</span>
          <span className="sub row" style={{ gap: 4 }}>Open the review queue <ArrowRight size={13} /></span>
        </Link>
        <div className="card stat">
          <span className="label"><span className="ico"><CheckCircle2 size={15} /></span>Files read successfully</span>
          <span className="value">{stats?.documents.success_rate != null ? `${(stats.documents.success_rate * 100).toFixed(1)}%` : stats ? "—" : <Skeleton h={32} w={70} />}</span>
          <span className="sub">{stats ? (failed ? <Link href="/documents?status=failed" style={{ color: "var(--red)" }}>{failed} could not be read: see why</Link> : `Average ${duration(stats.processing.avg_ms)} per file`) : ""}</span>
        </div>
      </div>

      {busy > 0 && (
        <div className="notice" style={{ marginBottom: 16 }}>
          <span className="spinner" style={{ marginTop: 2 }} />
          <span>{busy} file{busy > 1 ? "s are" : " is"} being processed right now. This page updates by itself.</span>
        </div>
      )}

      <div className="split">
        <div className="card">
          <div className="card-head">
            <div><h2>Recent documents</h2><p className="faint small">The last files uploaded and their status. Open one to see its data.</p></div>
            <Link href="/documents" className="btn btn-sm btn-ghost">See all <ArrowRight size={14} /></Link>
          </div>
          <div className="table-wrap" style={{ padding: "6px 8px 8px" }}>
            {docs === null ? <div style={{ padding: 16 }} className="stack"><Skeleton /><Skeleton /><Skeleton /></div> : docs.length === 0 ? (
              <Empty icon={<Upload size={22} />} title="Nothing uploaded yet">Upload invoices, scans, photos or spreadsheets, or process the sample files on the Upload page.</Empty>
            ) : (
              <table className="table">
                <tbody>
                  {docs.map((d) => (
                    <tr key={d.id} className="click" onClick={() => router.push(`/documents/${d.id}`)}>
                      <td style={{ width: 54 }}><Kind>{fileKind(d.filename, d.file_type)}</Kind></td>
                      <td><span className="fname" style={{ maxWidth: 260 }}>{d.filename}</span><span className="faint small">{when(d.created_at)}</span></td>
                      <td className="r hide-sm faint small num">{d.invoice_count} inv.</td>
                      <td className="r"><StatusPill status={d.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <div><h2>Waiting for a person</h2><p className="faint small">Invoices with a failed check or an unproven value.</p></div>
              <Link href="/review" className="btn btn-sm btn-ghost">Review <ArrowRight size={14} /></Link>
            </div>
            <div style={{ padding: "8px 22px 18px" }} className="stack">
              {review === null ? <Skeleton /> : review.length === 0 ? (
                <p className="muted small">Nothing to review. Every extracted invoice passed its checks or was approved.</p>
              ) : review.map((inv) => (
                <Link key={inv.id} href={`/documents/${inv.document_id}?invoice=${inv.id}`} className="mini-row">
                  <span style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 500 }}>{inv.invoice_number || "No number"}</span>
                    <span className="faint small" style={{ marginLeft: 8 }}>{inv.supplier_name || inv.document_filename}</span>
                  </span>
                  <span className="num small">{money(inv.total, inv.currency)}</span>
                </Link>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-head"><div><h2>Problems found</h2><p className="faint small">What the automatic checks caught, across all documents.</p></div></div>
            <div style={{ padding: "6px 22px 18px" }}>
              {!stats ? <Skeleton /> : errorsOnly.length === 0 ? <p className="muted small">No problems found yet.</p> : errorsOnly.map((i) => (
                <div className="hbar" key={i.code + i.severity}>
                  <div>
                    <span className="small">{issueTitle(i.code)}</span>
                    <div className="track"><span style={{ width: `${(i.count / maxIssue) * 100}%`, background: i.severity === "error" ? "#ef8a8a" : "#e9bb62" }} /></div>
                  </div>
                  <span className="num small r" style={{ textAlign: "right" }}>{i.count}</span>
                </div>
              ))}
              {stats && Object.keys(stats.cross_checks).length > 0 && (
                <>
                  <div className="divider" />
                  <Link href="/cross-checks" className="row between small">
                    <span className="muted">Cross-checks between documents</span>
                    <span className="row" style={{ gap: 6 }}>
                      {stats.cross_checks.match ? <span className="pill tone-green">{stats.cross_checks.match} match</span> : null}
                      {stats.cross_checks.mismatch ? <span className="pill tone-red">{stats.cross_checks.mismatch} differ</span> : null}
                      {stats.cross_checks.duplicate ? <span className="pill tone-amber">{stats.cross_checks.duplicate} duplicate</span> : null}
                    </span>
                  </Link>
                </>
              )}
            </div>
          </div>

          {stats && stats.value_by_currency.length > 0 && (
            <div className="card card-pad">
              <h2 style={{ fontSize: 17, marginBottom: 10 }}>Invoice value extracted</h2>
              <div className="stack" style={{ gap: 6 }}>
                {stats.value_by_currency.filter((v) => v.currency !== "unknown").map((v) => (
                  <div key={v.currency} className="row between small">
                    <span className="muted">{v.count} invoices in {v.currency}</span>
                    <span className="num" style={{ fontWeight: 500 }}>{money(v.total, v.currency)}</span>
                  </div>
                ))}
              </div>
              <p className="faint small" style={{ marginTop: 10 }}><Clock3 size={12} style={{ verticalAlign: -1 }} /> Slowest 5% of files took {duration(stats.processing.p95_ms)} or less.</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function Page() {
  return <Gate><Dashboard /></Gate>;
}
