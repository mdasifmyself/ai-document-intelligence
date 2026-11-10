"use client";
import { ArrowLeftRight, GitCompareArrows } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Gate } from "@/components/Gate";
import { Empty, ErrorNote, Kind, Skeleton } from "@/components/ui";
import { CheckSide, CrossCheck, getJSON } from "@/lib/api";
import { fileKind, money } from "@/lib/format";
import { FIELD, KIND } from "@/lib/labels";

const FILTERS = [["", "All"], ["mismatch", "Different values"], ["duplicate", "Duplicates"], ["match", "Matching"]] as const;
const TONE = { match: ["tone-green", "Values match"], mismatch: ["tone-red", "Values differ"], duplicate: ["tone-amber", "Duplicate"] } as const;

function Side({ s }: { s: CheckSide }) {
  const where = s.location?.pages ? `p. ${s.location.pages.join(", ")}` : s.location?.sheet ? `${s.location.sheet}${s.location.row ? `, row ${s.location.row}` : ""}` : "";
  return (
    <Link href={`/documents/${s.document_id}?invoice=${s.invoice_id}`} className="stack" style={{ gap: 4, minWidth: 0 }}>
      <span className="row" style={{ gap: 8, minWidth: 0 }}><Kind>{fileKind(s.filename || "", s.file_type)}</Kind><span className="fname" style={{ maxWidth: 220 }}>{s.filename}</span></span>
      <span className="faint small">{where} · {money(s.total, s.currency)}</span>
    </Link>
  );
}

function CrossChecks() {
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<CrossCheck[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    setRows(null);
    getJSON<CrossCheck[]>(`/cross-checks${status ? `?status=${status}` : ""}`).then(setRows).catch(setError);
  }, [status]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Cross-checks</h1>
          <p>The same invoice found in two documents, for example a PDF and the Excel ledger, or two PDFs. Each pair is compared field by field.</p>
        </div>
      </div>
      <ErrorNote error={error} />
      <div className="card">
        <div style={{ padding: "14px 18px 0" }}>
          <div className="seg">{FILTERS.map(([k, l]) => <button key={k} className={status === k ? "on" : ""} onClick={() => setStatus(k)}>{l}</button>)}</div>
        </div>
        <div className="table-wrap" style={{ padding: "8px 8px 8px" }}>
          {!rows ? <div className="stack" style={{ padding: 16 }}><Skeleton /><Skeleton /></div> : rows.length === 0 ? (
            <Empty icon={<GitCompareArrows size={22} />} title="No cross-checks yet">Upload an invoice and a spreadsheet that lists it (the sample ledger does this) to see the comparison.</Empty>
          ) : (
            <table className="table">
              <thead><tr><th>Invoice</th><th>Compared</th><th>Document A</th><th aria-hidden /><th>Document B</th><th>Result</th></tr></thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <td><b style={{ fontWeight: 500 }}>{c.a.invoice_number || c.b.invoice_number}</b><span className="faint small" style={{ display: "block" }}>{c.a.supplier_name || c.b.supplier_name}</span></td>
                    <td className="small muted">{KIND[c.kind] || c.kind}</td>
                    <td><Side s={c.a} /></td>
                    <td style={{ color: "var(--text-3)" }}><ArrowLeftRight size={15} /></td>
                    <td><Side s={c.b} /></td>
                    <td>
                      <span className={`pill ${TONE[c.status][0]}`}>{TONE[c.status][1]}</span>
                      {c.differences.map((d) => (
                        <div key={d.field} className="small" style={{ marginTop: 4, color: "var(--red)" }}>
                          {FIELD[d.field] || d.field}: {typeof d.a === "number" ? money(d.a) : String(d.a)} vs {typeof d.b === "number" ? money(d.b) : String(d.b)}
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}

export default function Page() {
  return <Gate><CrossChecks /></Gate>;
}
