"use client";
import { FileSpreadsheet } from "lucide-react";
import { useState } from "react";
import { blobUrl } from "@/lib/api";

/** Downloads a formatted Excel workbook. `query` narrows it (for example needs_review=true or document_id=…). */
export default function ExportButton({ query = "", label = "Export to Excel", small = false }: { query?: string; label?: string; small?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function run() {
    setBusy(true); setErr("");
    try {
      const url = await blobUrl(`/export.xlsx${query ? `?${query}` : ""}`);
      const a = document.createElement("a");
      a.href = url;
      a.download = `docintel-export-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
    } catch { setErr("The export could not be created. Try again."); } finally { setBusy(false); }
  }
  return (
    <span className="row" style={{ gap: 8 }}>
      <button className={`btn ${small ? "btn-sm" : ""}`} onClick={run} disabled={busy} title="Download a formatted Excel workbook: invoices, line items, problems, cross-checks and documents">
        <FileSpreadsheet size={small ? 14 : 16} /> {busy ? "Preparing…" : label}
      </button>
      {err && <span className="small" style={{ color: "var(--red)" }}>{err}</span>}
    </span>
  );
}
