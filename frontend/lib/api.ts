// Talks to the DocIntel API. The access code is kept in this browser only and sent as a header.
// Empty = same origin: Vercel forwards /api/* to the processing server (see next.config.ts), so the browser
// never needs the server's address. Set NEXT_PUBLIC_API_URL only to call an API on another origin directly.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
export const PREPARED_FOR = process.env.NEXT_PUBLIC_PREPARED_FOR || "";
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || "";
const KEY = "docintel.access";

export type Status = "queued" | "processing" | "completed" | "needs_review" | "failed";
export type Severity = "error" | "warning" | "info";

export interface Issue { id: number; invoice_id: string | null; code: string; severity: Severity; field: string | null; message: string; details: Record<string, unknown> }
export interface FieldMeta { value: unknown; evidence: string | null; raw: string | null; verified: boolean | null; confidence: number; source: string; suggested?: unknown }
export interface LineItem { description: string; quantity: number | null; unit_price: number | null; amount: number | null; evidence?: string | null; verified?: boolean }
export interface Correction { id: number; field: string; old_value: unknown; new_value: unknown; reason: string | null; corrected_by: string; created_at: string }
export interface Invoice {
  id: string; document_id: string; seq: number; source_kind: "document" | "record"; location: { pages?: number[]; sheet?: string; row?: number };
  invoice_number: string | null; invoice_date: string | null; supplier_name: string | null; customer_name: string | null;
  subtotal: number | null; tax: number | null; total: number | null; currency: string | null; line_items: LineItem[];
  fields: Record<string, FieldMeta>; extraction_method: string | null; model: string | null; confidence: number | null;
  status: "ok" | "needs_review" | "reviewed"; needs_review: boolean; reviewed_at: string | null; updated_at: string | null;
  issues?: Issue[]; corrections?: Correction[]; document_filename?: string | null; document_file_type?: string | null;
}
export interface Doc {
  id: string; filename: string; file_type: string | null; size_bytes: number; status: Status;
  progress: { stage?: string; done?: number; total?: number }; page_count: number | null; text_method: string | null;
  ocr_confidence: number | null; invoice_count: number; issue_count: number; error_code: string | null; error_message: string | null;
  attempts: number; duplicate_of: string | null; created_at: string; finished_at: string | null; processing_ms: number | null; batch_id: string | null;
}
export interface PageInfo { page_no: number; label: string | null; method: string; ocr_confidence: number | null; rotation: number | null; deskew_angle: number | null; chars: number }
export interface EventItem { id: number; stage: string; status: string; message: string | null; duration_ms: number | null; created_at: string }
export interface DocDetail extends Doc { sha256: string; ai_calls: number; pages: PageInfo[]; invoices: Invoice[]; issues: Issue[]; events: EventItem[] }
export interface Paged<T> { items: T[]; total: number; page: number; page_size: number }
export interface SearchHit { invoice: Invoice; document_filename: string; document_file_type: string | null; score: number; match: "keyword" | "semantic" | "hybrid"; snippet: string | null }
export interface CrossCheck { id: number; kind: string; status: "match" | "mismatch" | "duplicate"; differences: { field: string; a: unknown; b: unknown }[]; created_at: string; a: CheckSide; b: CheckSide }
export interface CheckSide { invoice_id: string; invoice_number: string | null; supplier_name: string | null; total: number | null; currency: string | null; invoice_date: string | null; document_id: string | null; filename: string | null; file_type: string | null; location: Invoice["location"] | null }
export interface Stats {
  documents: { total: number; by_status: Record<string, number>; by_type: Record<string, number>; pages: number; success_rate: number | null };
  invoices: { total: number; needs_review: number; reviewed: number; by_method: Record<string, number> };
  processing: { avg_ms: number | null; p95_ms: number | null; waiting_in_queue: number; processing_now: number };
  issues: { code: string; severity: Severity; count: number }[];
  value_by_currency: { currency: string; total: number; count: number }[];
  cross_checks: Record<string, number>;
}
export interface Meta { app: string; version: string; allowed_extensions: string[]; max_file_mb: number; max_files_per_upload: number; max_pages: number; extraction_model: string; vision_model: string; embedding_model: string; prompt_version: string; access_code_required: boolean }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Plain-language message for any failed request. */
export function friendly(status: number, detail?: string): string {
  if (status === 0) return "Can’t reach the server. Check your internet connection; the page retries by itself.";
  if (status === 401) return "The access code was not accepted. Enter the code again (it is in the email that shared this demo).";
  if (status === 413) return detail || "The upload is too large. Use files up to 50 MB, at most 50 at a time.";
  if (status === 429) return "Too many requests in a short time. Please wait a minute and try again.";
  if (status === 404) return detail || "This item no longer exists. It may have been deleted.";
  if (status === 409) return detail || "This document is being processed right now. Try again when it finishes.";
  if (status === 422) return detail || "Some values are not valid. Check them and try again.";
  if (status >= 500) return "The processing server is busy or restarting. The page retries by itself; if it continues, wait a minute.";
  return detail || "Something went wrong. Please try again.";
}

// The code is kept for this browser session only, so every new session starts at the lock screen.
// Older builds kept it permanently in localStorage; that copy is removed so those browsers are locked again too.
if (typeof window !== "undefined") { try { localStorage.removeItem(KEY); } catch { /* private mode */ } }

export function getCode(): string {
  try { return sessionStorage.getItem(KEY) || ""; } catch { return ""; }
}
export function setCode(code: string) {
  try { code ? sessionStorage.setItem(KEY, code) : sessionStorage.removeItem(KEY); } catch { /* private mode */ }
  window.dispatchEvent(new Event("docintel-access"));
}
/** Locks the demo in this browser: the lock screen shows until the code is entered again. */
export function lockDemo() { setCode(""); }

function headers(extra?: HeadersInit): HeadersInit {
  const code = getCode();
  return { ...(code ? { "X-Access-Code": code } : {}), ...(extra || {}) };
}

async function handle<T>(r: Response): Promise<T> {
  if (r.status === 204) return undefined as T;
  if (!r.ok) {
    let detail: string | undefined;
    try { const j = await r.json(); detail = typeof j.detail === "string" ? j.detail : undefined; } catch { /* not json */ }
    throw new ApiError(r.status, friendly(r.status, detail));
  }
  return r.json();
}

const RETRYABLE = new Set([0, 502, 503, 504]);
const wait = (ms: number) => new Promise((res) => setTimeout(res, ms));

/** Reads (and idempotent edits) are retried automatically on network errors and short server restarts. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const retries = method === "GET" || method === "PATCH" ? 3 : 0;
  for (let attempt = 0; ; attempt++) {
    let status = 0;
    try {
      const r = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers: headers(init.headers) });
      status = r.status;
      if (!RETRYABLE.has(status) || attempt >= retries) {
        signalHealth(status < 500);
        return await handle<T>(r);
      }
    } catch (e) {
      if (e instanceof ApiError) throw e;
      if (attempt >= retries) { signalHealth(false); throw new ApiError(0, friendly(0)); }
    }
    await wait([600, 1500, 3500][attempt] || 3500);
  }
}

/** Lets the app show one calm "reconnecting" notice instead of errors on every card. */
function signalHealth(ok: boolean) {
  try { window.dispatchEvent(new CustomEvent("docintel-health", { detail: ok })); } catch { /* server render */ }
}

export const getJSON = <T,>(path: string) => api<T>(path);
export const postJSON = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), headers: { "Content-Type": "application/json" } });
export const patchJSON = <T,>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
export const del = (path: string) => api<void>(path, { method: "DELETE" });

export async function blobUrl(path: string): Promise<string> {
  for (let attempt = 0; ; attempt++) {
    const r = await fetch(`${API_URL}/api/v1${path}`, { headers: headers() }).catch(() => null);
    if (r && r.ok) return URL.createObjectURL(await r.blob());
    const status = r ? r.status : 0;
    if (!RETRYABLE.has(status) || attempt >= 2) throw new ApiError(status, friendly(status));
    await wait([800, 2000][attempt]);
  }
}

export interface UploadResponse { batch_id: string; accepted: Doc[]; rejected: { filename: string; code: string; message: string }[] }

/** Upload with progress (fetch has no upload progress, so XMLHttpRequest is used). */
export function uploadFiles(files: File[], onProgress: (pct: number) => void): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/v1/documents`);
    const code = getCode();
    if (code) xhr.setRequestHeader("X-Access-Code", code);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText || "{}");
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else reject(new ApiError(xhr.status, friendly(xhr.status, typeof body.detail === "string" ? body.detail : undefined)));
      } catch { reject(new ApiError(xhr.status, friendly(xhr.status))); }
    };
    xhr.onerror = () => reject(new ApiError(0, "The upload could not reach the server. Check your connection and press Upload again."));
    xhr.send(fd);
  });
}
