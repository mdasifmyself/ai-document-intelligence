"use client";
import { Activity, AlertCircle, Brain, CheckCircle2, Cpu, History, Layers, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Gate } from "@/components/Gate";
import { ErrorNote, Skeleton, useToast } from "@/components/ui";
import { getJSON, postJSON } from "@/lib/api";
import { when } from "@/lib/format";
import { ACTION, ISSUE } from "@/lib/labels";

interface Status {
  checked_at: string;
  queue: { waiting?: number; failed_jobs_in_registry?: number; error?: string };
  workers: { name: string; state: string; current_job: string | null; last_heartbeat: string | null }[];
  ai: { last_ok?: { at: string; detail: string }; last_error?: { at: string; detail: string }; calls_today?: number; daily_limit?: number };
  recovery: { at: string; requeued: number; failed: number; lost_requeued: number } | null;
  documents: {
    slow_or_stuck: { id: string; filename: string; stage: string | null; last_sign_of_life: string | null }[];
    stale_after_minutes: number;
    failed_by_code: Record<string, number>;
    recent_failures: { id: string; filename: string; code: string | null; message: string | null; attempts: number; at: string | null }[];
    recent_recoveries: { document_id: string; message: string; at: string }[];
  };
}

function Light({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return ok ? <CheckCircle2 size={18} color="var(--green)" /> : <AlertCircle size={18} color={warn ? "var(--amber)" : "var(--red)"} />;
}

function SystemPage() {
  const [s, setS] = useState<Status | null>(null);
  const [error, setError] = useState<unknown>(null);
  const toast = useToast();
  const load = useCallback(() => getJSON<Status>("/system/status").then((x) => { setS(x); setError(null); }).catch(setError), []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  async function retry(codes?: string) {
    const r = await postJSON<{ requeued: number }>(`/jobs/reprocess-failed${codes ? `?codes=${codes}` : ""}`);
    toast.show(`${r.requeued} document${r.requeued === 1 ? "" : "s"} sent back to the queue`);
    load();
  }

  if (!s) return <><ErrorNote error={error} /><div className="stack"><Skeleton h={36} w={240} /><Skeleton h={160} /></div></>;
  const workersUp = s.workers.length;
  const aiOk = !!s.ai.last_ok && (!s.ai.last_error || s.ai.last_ok.at > s.ai.last_error.at);
  const retryable = Object.entries(s.documents.failed_by_code).filter(([c]) => ["AI_UNAVAILABLE", "JOB_TIMEOUT", "WORKER_ERROR", "WORKER_LOST", "INTERNAL_ERROR"].includes(c));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>System health</h1>
          <p>Workers, backlog, AI service and failures, with what to do when something is wrong. Updates every 5 seconds.</p>
        </div>
        <span className="faint small">Checked {when(s.checked_at)}</span>
      </div>
      <ErrorNote error={error} />

      <div className="grid g-4" style={{ marginBottom: 16 }}>
        <div className="card stat">
          <span className="label"><Light ok={workersUp > 0} />Workers</span>
          <span className="value">{workersUp}</span>
          <span className="sub">{s.workers.filter((w) => w.state === "busy").length} busy right now</span>
        </div>
        <div className="card stat">
          <span className="label"><Light ok={!s.queue.error && (s.queue.waiting ?? 0) < 50} warn />Backlog</span>
          <span className="value">{s.queue.error ? "—" : s.queue.waiting}</span>
          <span className="sub">{s.queue.error || "files waiting for a worker"}</span>
        </div>
        <div className="card stat">
          <span className="label"><Light ok={aiOk} warn={!s.ai.last_ok} />AI service</span>
          <span className="value" style={{ fontSize: 22 }}>{aiOk ? "Answering" : s.ai.last_error ? "Errors" : "No calls yet"}</span>
          <span className="sub">{s.ai.calls_today ?? 0} of {s.ai.daily_limit ?? "—"} calls used today</span>
        </div>
        <div className="card stat">
          <span className="label"><Light ok={s.documents.slow_or_stuck.length === 0} warn />Stuck files</span>
          <span className="value">{s.documents.slow_or_stuck.length}</span>
          <span className="sub">recovered automatically after {s.documents.stale_after_minutes} min</span>
        </div>
      </div>

      <div className="split">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h2 className="row" style={{ gap: 8 }}><AlertCircle size={18} /> Recent failures</h2>
              {retryable.length > 0 && <button className="btn btn-sm" onClick={() => retry(retryable.map(([c]) => c).join(","))}><RotateCcw size={14} /> Retry the retryable ones</button>}
            </div>
            <div style={{ padding: "8px 22px 18px" }}>
              {s.documents.recent_failures.length === 0 ? <p className="muted small">No failed documents.</p> : s.documents.recent_failures.map((f) => (
                <Link key={f.id} href={`/documents/${f.id}`} style={{ display: "block", padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                  <div className="row between"><span className="fname" style={{ maxWidth: 300 }}>{f.filename}</span><span className="pill tone-red">{ISSUE[f.code || ""]?.title || f.code}</span></div>
                  <div className="small muted" style={{ marginTop: 3 }}>{f.message}</div>
                  {f.code && ACTION[f.code] && <div className="small" style={{ marginTop: 3 }}><b style={{ fontWeight: 600 }}>What to do:</b> {ACTION[f.code]}</div>}
                </Link>
              ))}
              {Object.keys(s.documents.failed_by_code).length > 0 && (
                <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
                  {Object.entries(s.documents.failed_by_code).map(([c, n]) => <span key={c} className="pill">{ISSUE[c]?.title || c}: {n}</span>)}
                </div>
              )}
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h2 className="row" style={{ gap: 8 }}><History size={18} /> Automatic recoveries</h2>
              <span className="faint small">{s.recovery ? `last check ${when(s.recovery.at)}` : "first check within 2 minutes"}</span></div>
            <div style={{ padding: "8px 22px 18px" }}>
              {s.documents.recent_recoveries.length === 0 ? <p className="muted small">Nothing needed recovering. The system checks every 2 minutes for files that got stuck (for example after a restart) and puts them back in the queue.</p>
                : s.documents.recent_recoveries.map((r, i) => (
                  <Link key={i} href={`/documents/${r.document_id}`} className="small" style={{ display: "block", padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
                    <span className="muted">{r.message}</span> <span className="faint">· {when(r.at)}</span>
                  </Link>
                ))}
            </div>
          </div>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head"><h2 className="row" style={{ gap: 8 }}><Cpu size={18} /> Workers</h2></div>
            <div style={{ padding: "8px 22px 18px" }}>
              {s.workers.length === 0 ? <div className="notice err small">No worker is running. Files will wait in the queue. Restart the worker service.</div> : s.workers.map((w) => (
                <div key={w.name} className="row between small" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
                  <span className="row" style={{ gap: 8 }}><Layers size={15} color="var(--text-3)" /> Worker {w.name}</span>
                  <span className="row" style={{ gap: 8 }}>
                    <span className={`pill ${w.state === "busy" ? "tone-blue" : "tone-green"}`}>{w.state === "busy" ? "Working" : "Ready"}</span>
                    <span className="faint">{w.last_heartbeat ? `seen ${when(w.last_heartbeat)}` : ""}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h2 className="row" style={{ gap: 8 }}><Brain size={18} /> AI service</h2></div>
            <div style={{ padding: "8px 22px 18px" }} className="stack small">
              <div className="row between"><span className="muted">Last successful call</span><span>{s.ai.last_ok ? when(s.ai.last_ok.at) : "—"}</span></div>
              <div className="row between"><span className="muted">Last error</span><span>{s.ai.last_error ? when(s.ai.last_error.at) : "none"}</span></div>
              {s.ai.last_error && !aiOk && <div className="notice warn small">{s.ai.last_error.detail}. Files that failed with “AI service unavailable” can be retried once it answers again.</div>}
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h2 className="row" style={{ gap: 8 }}><Activity size={18} /> Slow or stuck right now</h2></div>
            <div style={{ padding: "8px 22px 18px" }}>
              {s.documents.slow_or_stuck.length === 0 ? <p className="muted small">Every file in progress is moving.</p> : s.documents.slow_or_stuck.map((d) => (
                <Link key={d.id} href={`/documents/${d.id}`} className="row between small" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
                  <span className="fname" style={{ maxWidth: 220 }}>{d.filename}</span><span className="faint">no update {when(d.last_sign_of_life)}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
      {toast.node}
    </>
  );
}

export default function Page() {
  return <Gate><SystemPage /></Gate>;
}
