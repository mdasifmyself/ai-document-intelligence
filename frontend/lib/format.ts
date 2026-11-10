export function money(v: number | null | undefined, currency?: string | null) {
  if (v === null || v === undefined) return "—";
  const s = v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${currency} ${s}` : s;
}

export function bytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function duration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

export function when(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function dateText(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function pct(v: number | null | undefined, digits = 0) {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;
}

export function fileKind(name: string, type?: string | null) {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  if (type === "pdf" || ext === "pdf") return "PDF";
  if (["xlsx", "xls"].includes(ext) || type === "xlsx" || type === "xls") return ext.toUpperCase();
  if (ext === "csv" || type === "csv") return "CSV";
  if (["tif", "tiff"].includes(ext)) return "TIFF";
  if (["jpg", "jpeg"].includes(ext)) return "JPG";
  if (ext === "png") return "PNG";
  return ext.toUpperCase() || "FILE";
}
