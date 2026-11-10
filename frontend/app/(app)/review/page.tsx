"use client";
import { ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Gate } from "@/components/Gate";
import ExportButton from "@/components/ExportButton";
import { Empty, ErrorNote, Skeleton } from "@/components/ui";
import { getJSON, Invoice, Paged } from "@/lib/api";
import { dateText, money } from "@/lib/format";
import { issueTitle } from "@/lib/labels";

type Row = Invoice & { document_filename?: string; issue_codes?: string[] };

function Review() {
  const router = useRouter();
  const [data, setData] = useState<Paged<Row> | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    getJSON<Paged<Row>>(`/invoices?needs_review=true&page=${page}&page_size=25`).then((d) => { setData(d); setError(null); }).catch(setError);
  }, [page]);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Review queue</h1>
          <p>Invoices where a check failed or a value could not be proven. Open one, compare it with the page, fix what is wrong and approve it.</p>
        </div>
        <ExportButton query="needs_review=true" label="Export review list" />
      </div>
      <ErrorNote error={error} />
      <div className="card">
        <div className="table-wrap">
          {!data ? <div className="stack" style={{ padding: 20 }}><Skeleton /><Skeleton /><Skeleton /></div> : data.items.length === 0 ? (
            <Empty icon={<ShieldCheck size={22} />} title="Nothing to review">Every extracted invoice passed its checks or was approved by a person.</Empty>
          ) : (
            <table className="table">
              <thead><tr><th>Invoice</th><th className="hide-sm">Supplier</th><th className="hide-sm">Date</th><th className="r hide-sm">Total</th><th className="hide-sm">Why it needs a look</th></tr></thead>
              <tbody>
                {data.items.map((i) => {
                  const codes = i.issue_codes || [];
                  return (
                    <tr key={i.id} className="click" onClick={() => router.push(`/documents/${i.document_id}?invoice=${i.id}`)}>
                      <td>
                        <span style={{ fontWeight: 500 }}>{i.invoice_number || "No number"}</span><span className="faint small fname" style={{ maxWidth: 220 }}>{i.document_filename}</span>
                        <span className="show-sm" style={{ marginTop: 6, gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                          <span className="num small" style={{ fontWeight: 500 }}>{money(i.total, i.currency)}</span>
                          {(i.issue_codes || []).slice(0, 2).map((c) => <span key={c} className="pill tone-amber">{issueTitle(c)}</span>)}
                        </span>
                      </td>
                      <td className="hide-sm">{i.supplier_name || <span className="faint">—</span>}</td>
                      <td className="hide-sm num small nowrap">{dateText(i.invoice_date)}</td>
                      <td className="r num hide-sm">{money(i.total, i.currency)}</td>
                      <td className="hide-sm">
                        <div className="row wrap" style={{ gap: 6 }}>
                          {codes.slice(0, 2).map((c) => <span key={c} className={`pill ${["MISSING_FIELD", "TOTAL_MISMATCH", "LINE_ITEMS_MISMATCH", "LINE_ITEM_MATH", "DUPLICATE_INVOICE", "CROSS_CHECK_MISMATCH", "INVALID_AMOUNT"].includes(c) ? "tone-red" : "tone-amber"}`}>{issueTitle(c)}</span>)}
                          {codes.length > 2 && <span className="faint small">+{codes.length - 2}</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
        {data && data.total > data.page_size && (
          <div className="row between" style={{ padding: "12px 18px" }}>
            <span className="faint small">{data.total} invoices waiting</span>
            <span className="row">
              <button className="btn btn-sm" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
              <button className="btn btn-sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</button>
            </span>
          </div>
        )}
      </div>
    </>
  );
}

export default function Page() {
  return <Gate><Review /></Gate>;
}
