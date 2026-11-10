"use client";
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import type { Issue } from "@/lib/api";
import { ACTION, ISSUE, STATUS } from "@/lib/labels";

export function StatusPill({ status, title }: { status: string; title?: string }) {
  const s = STATUS[status] || { label: status, tone: "neutral", hint: "" };
  return (
    <span className={`pill tone-${s.tone}`} title={title || s.hint}>
      {status === "processing" || status === "queued" ? <span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} /> : <span className="dot" />}
      {s.label}
    </span>
  );
}

export function Kind({ children }: { children: ReactNode }) {
  return <span className="kind">{children}</span>;
}

export function Confidence({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return null;
  const pct = Math.round(value * 100);
  return (
    <span className={`conf ${pct < 70 ? "low" : ""}`} title={`Confidence ${pct}%: how sure the system is, based on the proof found in the document and the reading quality.`}>
      <span className="bar"><span style={{ width: `${pct}%` }} /></span>
      <span className="num">{pct}%</span>
    </span>
  );
}

export function IssueItem({ issue }: { issue: Issue }) {
  const Icon = issue.severity === "error" ? AlertCircle : issue.severity === "warning" ? AlertTriangle : Info;
  const meta = ISSUE[issue.code];
  return (
    <div className={`issue ${issue.severity}`}>
      <Icon size={18} strokeWidth={1.9} style={{ marginTop: 1 }} />
      <div>
        <div className="t">{meta?.title || issue.code}</div>
        <div className="m">{issue.message}</div>
        {issue.severity !== "info" && ACTION[issue.code] && (
          <div className="fix"><b>What to do:</b> <span>{ACTION[issue.code]}</span></div>
        )}
      </div>
    </div>
  );
}

export function Issues({ issues, empty = "No problems found. Every check passed." }: { issues: Issue[]; empty?: string }) {
  if (!issues.length) {
    return (
      <div className="issue info" style={{ background: "var(--green-50)" }}>
        <CheckCircle2 size={18} strokeWidth={1.9} color="var(--green)" style={{ marginTop: 1 }} />
        <div className="m" style={{ marginTop: 0, color: "var(--ink)" }}>{empty}</div>
      </div>
    );
  }
  const order = { error: 0, warning: 1, info: 2 } as const;
  return <div>{[...issues].sort((a, b) => order[a.severity] - order[b.severity]).map((i) => <IssueItem key={i.id} issue={i} />)}</div>;
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="big-ico">{icon}</div>
      <h3>{title}</h3>
      {children && <div className="muted small" style={{ maxWidth: 420 }}>{children}</div>}
    </div>
  );
}

export function Skeleton({ h = 18, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} />;
}

export function Toast({ text, onDone }: { text: string; onDone: () => void }) {
  useEffect(() => { const t = setTimeout(onDone, 2600); return () => clearTimeout(t); }, [onDone]);
  return <div className="toast" role="status">{text}</div>;
}

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const node = msg ? <Toast text={msg} onDone={() => setMsg(null)} /> : null;
  return { show: setMsg, node };
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="notice err"><AlertCircle size={18} /> <span>{msg}</span></div>;
}
