"use client";
import { Check, CheckCheck, Pencil, Quote, Undo2 } from "lucide-react";
import { useState } from "react";
import { Confidence, Issues } from "@/components/ui";
import { Invoice, patchJSON, postJSON } from "@/lib/api";
import { dateText, money, when } from "@/lib/format";
import { FIELD, METHOD } from "@/lib/labels";

const ORDER = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"] as const;
const AMOUNTS = new Set(["subtotal", "tax", "total"]);

function show(inv: Invoice, f: string) {
  const v = inv[f as keyof Invoice] as unknown;
  if (v === null || v === undefined) return null;
  if (AMOUNTS.has(f)) return money(v as number);
  if (f === "invoice_date") return dateText(v as string);
  return String(v);
}

export default function InvoicePanel({ inv, onChange, toast }: { inv: Invoice; onChange: (i: Invoice) => void; toast: (m: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const issues = inv.issues || [];
  const flagged = new Set(issues.filter((i) => i.severity !== "info").map((i) => i.field));
  const isRecord = inv.source_kind === "record";
  const fields = ORDER.filter((f) => !isRecord || inv.fields[f] !== undefined || inv[f as keyof Invoice] != null);

  function start() {
    const d: Record<string, string> = {};
    fields.forEach((f) => { const v = inv[f as keyof Invoice]; d[f] = v === null || v === undefined ? "" : String(v); });
    setDraft(d); setReason(""); setErr(""); setEditing(true);
  }

  async function save() {
    const changed: Record<string, string | null> = {};
    fields.forEach((f) => {
      const before = inv[f as keyof Invoice];
      const now = draft[f]?.trim() ?? "";
      if ((before === null || before === undefined ? "" : String(before)) !== now) changed[f] = now === "" ? null : now;
    });
    if (!Object.keys(changed).length) { setEditing(false); return; }
    setBusy(true); setErr("");
    try {
      const r = await patchJSON<Invoice>(`/invoices/${inv.id}`, { fields: changed, reason: reason || null, corrected_by: "Demo reviewer" });
      onChange(r); setEditing(false); toast("Saved. The checks ran again.");
      window.dispatchEvent(new Event("docintel-refresh"));
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }

  async function approve() {
    setBusy(true);
    try {
      const r = await postJSON<Invoice>(`/invoices/${inv.id}/approve?reviewer=Demo%20reviewer`);
      onChange(r); toast("Approved and marked as reviewed.");
      window.dispatchEvent(new Event("docintel-refresh"));
    } finally { setBusy(false); }
  }

  const toCheck = issues.filter((i) => i.severity !== "info");
  const summary = [
    `${inv.source_kind === "record" ? "Spreadsheet row for invoice" : "Invoice"} ${inv.invoice_number || "(no number)"}`,
    inv.supplier_name ? ` from ${inv.supplier_name}` : "",
    inv.customer_name ? ` to ${inv.customer_name}` : "",
    inv.invoice_date ? `, dated ${dateText(inv.invoice_date)}` : "",
    inv.total != null ? `, total ${money(inv.total, inv.currency)}` : "",
    inv.line_items?.length ? `, ${inv.line_items.length} line item${inv.line_items.length === 1 ? "" : "s"}` : "",
    ". ",
    inv.status === "reviewed" ? "Approved by a person." : toCheck.length ? `${toCheck.length} thing${toCheck.length === 1 ? "" : "s"} to check below.` : "Every check passed.",
  ].join("");
  const loc = inv.location || {};
  const where = loc.pages ? `Page${loc.pages.length > 1 ? "s" : ""} ${loc.pages.join(", ")}` : loc.sheet ? `Sheet “${loc.sheet}”${loc.row ? `, row ${loc.row}` : ""}` : "";

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card">
        <div className="card-head">
          <div>
            <h2>{inv.invoice_number || "Invoice without a number"}</h2>
            <p className="faint small" style={{ marginTop: 2 }}>{[where, METHOD[inv.extraction_method || ""] || inv.extraction_method, inv.model].filter(Boolean).join(" · ")}</p>
          </div>
          <div className="row" style={{ gap: 6 }}>
            {!editing && <button className="btn btn-sm" onClick={start}><Pencil size={14} /> Edit</button>}
            {!editing && inv.status !== "reviewed" && (
              <button className="btn btn-sm btn-dark" onClick={approve} disabled={busy}><CheckCheck size={14} /> Approve</button>
            )}
            {inv.status === "reviewed" && <span className="pill tone-green"><Check size={13} /> Approved {when(inv.reviewed_at)}</span>}
          </div>
        </div>
        <div style={{ padding: "6px 22px 14px" }}>
          <p className="summary-line">{summary}</p>
          {toCheck.length > 0 && !editing && (
            <div style={{ margin: "10px 0 6px" }}>
              <div className="faint small" style={{ marginBottom: 6 }}>Needs your attention</div>
              <Issues issues={toCheck} />
            </div>
          )}
          <div className="fields">
            {fields.map((f) => {
              const meta = inv.fields[f];
              const value = show(inv, f);
              const unproven = meta?.verified === false;
              return (
                <div className="field-row" key={f}>
                  <span className="k">{FIELD[f]}</span>
                  <div style={{ minWidth: 0 }}>
                    {editing ? (
                      <input className="edit-input" value={draft[f] ?? ""} onChange={(e) => setDraft({ ...draft, [f]: e.target.value })}
                        placeholder={f === "invoice_date" ? "YYYY-MM-DD" : AMOUNTS.has(f) ? "0.00" : f === "currency" ? "USD" : ""} aria-label={FIELD[f]} />
                    ) : (
                      <>
                        <span className={`v ${value === null ? "empty" : ""} ${flagged.has(f) && value !== null ? "flag" : ""}`}>
                          {value ?? (unproven ? `Removed: no proof in the document${meta?.suggested != null ? ` (AI suggested “${String(meta?.suggested)}”)` : ""}` : meta?.raw ? `Unclear: “${meta.raw}”` : "Not on the document")}
                        </span>
                        {meta?.evidence && (
                          <div className="proof"><Quote size={11} style={{ flex: "none", transform: "translateY(1px)" }} />
                            <span>{meta.source === "manual" ? meta.evidence : <q>{meta.evidence}</q>}{meta.source === "vision+text" ? " · confirmed by two readings" : meta.source === "vision" ? " · read from the image" : meta.source === "cell" ? "" : ""}</span></div>
                        )}
                      </>
                    )}
                  </div>
                  {!editing && value !== null && <Confidence value={meta?.confidence} />}
                </div>
              );
            })}
          </div>
          {editing && (
            <div className="stack" style={{ marginTop: 12 }}>
              <input className="input" placeholder="Why are you changing it? (optional, saved in the history)" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" />
              {err && <div className="notice err small">{err}</div>}
              <div className="row">
                <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save corrections"}</button>
                <button className="btn btn-ghost" onClick={() => setEditing(false)}><Undo2 size={14} /> Cancel</button>
              </div>
            </div>
          )}
        </div>
      </div>

      {issues.some((i) => i.severity === "info") || toCheck.length === 0 ? (
        <div className="card">
          <div className="card-head"><h2>Checks</h2><span className="faint small">{toCheck.length ? "notes" : "all passed"}</span></div>
          <div style={{ padding: "12px 22px 20px" }}><Issues issues={issues.filter((i) => i.severity === "info")} empty="Every check passed: required values present, totals add up, no duplicates or conflicts found." /></div>
        </div>
      ) : null}

      {inv.line_items?.length > 0 && (
        <div className="card">
          <div className="card-head"><h2>Line items</h2><span className="faint small">{inv.line_items.length}</span></div>
          <div className="table-wrap" style={{ padding: "4px 8px 8px" }}>
            <table className="table">
              <thead><tr><th>Description</th><th className="r">Qty</th><th className="r">Unit price</th><th className="r">Amount</th></tr></thead>
              <tbody>
                {inv.line_items.map((li, i) => {
                  const wrong = li.quantity != null && li.unit_price != null && li.amount != null && Math.abs(li.quantity * li.unit_price - li.amount) > 0.02;
                  return (
                    <tr key={i}>
                      <td>{li.description}</td>
                      <td className="r num">{li.quantity ?? "—"}</td>
                      <td className="r num">{money(li.unit_price)}</td>
                      <td className="r num" style={wrong ? { color: "var(--red)", fontWeight: 500 } : undefined}>{money(li.amount)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(inv.corrections?.length || 0) > 0 && (
        <div className="card">
          <div className="card-head"><h2>Changes by people</h2></div>
          <div style={{ padding: "8px 22px 18px" }} className="stack">
            {inv.corrections!.map((c) => (
              <div key={c.id} className="small" style={{ borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
                <b style={{ fontWeight: 500 }}>{c.field === "status" ? "Status" : FIELD[c.field] || c.field}</b>{" "}
                <span className="muted">{String(c.old_value ?? "empty")} → {String(c.new_value ?? "empty")}</span>
                <div className="faint">{c.corrected_by} · {when(c.created_at)}{c.reason ? ` · “${c.reason}”` : ""}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
