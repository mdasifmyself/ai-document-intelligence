"use client";
import { ChevronLeft, ChevronRight, FileSpreadsheet } from "lucide-react";
import { useEffect, useState } from "react";
import { blobUrl, DocDetail, getJSON } from "@/lib/api";
import { METHOD } from "@/lib/labels";

/** Shows the original: page images for PDFs and images, the sheet content for spreadsheets. */
export default function DocViewer({ doc, page, onPage }: { doc: DocDetail; page: number; onPage: (n: number) => void }) {
  const [src, setSrc] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const total = doc.pages.length;
  const info = doc.pages.find((p) => p.page_no === page);
  const visual = doc.file_type === "pdf" || doc.file_type === "image";

  useEffect(() => {
    let url: string | null = null;
    let alive = true;
    setFailed(false); setSrc(null); setText(null);
    if (!total) return;
    if (visual) {
      blobUrl(`/documents/${doc.id}/pages/${page}/image`).then((u) => { url = u; alive ? setSrc(u) : URL.revokeObjectURL(u); }).catch(() => alive && setFailed(true));
    } else {
      getJSON<{ text: string }>(`/documents/${doc.id}/pages/${page}`).then((p) => alive && setText(p.text)).catch(() => alive && setFailed(true));
    }
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [doc.id, page, total, visual]);

  return (
    <div className="card viewer">
      <div className="card-head" style={{ paddingBottom: 12 }}>
        <h2 style={{ fontSize: 15 }}>
          {visual ? `Page ${page} of ${total}` : info?.label ? `Sheet “${info.label}”` : `Sheet ${page}`}
        </h2>
        <div className="row" style={{ gap: 6 }}>
          {info && <span className="pill">{METHOD[info.method] || info.method}{info.ocr_confidence != null ? ` · ${Math.round(info.ocr_confidence)}%` : ""}</span>}
          {total > 1 && (
            <>
              <button className="btn icon-btn btn-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={16} /></button>
              <button className="btn icon-btn btn-sm" aria-label="Next page" disabled={page >= total} onClick={() => onPage(page + 1)}><ChevronRight size={16} /></button>
            </>
          )}
        </div>
      </div>
      <div style={{ padding: "0 14px 14px" }}>
        <div className="viewer-stage">
          {!total ? <p className="muted small">No preview: the file could not be read.</p>
            : failed ? <p className="muted small">The preview could not be loaded.</p>
            : visual ? (src ? <img src={src} alt={`Page ${page} of ${doc.filename}`} /> : <div className="spinner" />)
            : text !== null ? <div className="sheet-text">{text || "This sheet is empty."}</div> : <div className="spinner" />}
        </div>
        {!visual && total > 1 && (
          <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
            {doc.pages.map((p) => (
              <button key={p.page_no} className={`btn btn-sm ${p.page_no === page ? "btn-dark" : ""}`} onClick={() => onPage(p.page_no)}>
                <FileSpreadsheet size={14} /> {p.label || `Sheet ${p.page_no}`}
              </button>
            ))}
          </div>
        )}
        {info && (info.rotation || info.deskew_angle) ? (
          <p className="faint small" style={{ marginTop: 8 }}>
            Before reading, the scan was {info.rotation ? `turned ${info.rotation}°` : ""}{info.rotation && info.deskew_angle ? " and " : ""}{info.deskew_angle ? `straightened by ${Math.abs(info.deskew_angle).toFixed(1)}°` : ""}.
          </p>
        ) : null}
      </div>
    </div>
  );
}
