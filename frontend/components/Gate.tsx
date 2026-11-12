"use client";
import { KeyRound } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import { ApiError, getCode, getJSON, setCode } from "@/lib/api";

/** Asks for the demo access code once; stores it in this browser only. A link with ?code=... fills it in. */
export function useAccess() {
  const [code, setState] = useState<string | null>(null);
  useEffect(() => {
    const url = new URL(window.location.href);
    const fromLink = url.searchParams.get("code");
    if (fromLink) {
      setCode(fromLink);
      url.searchParams.delete("code");
      window.history.replaceState({}, "", url.pathname + (url.search ? url.search : "") + url.hash);
    }
    const sync = () => setState(getCode());
    sync();
    window.addEventListener("docintel-access", sync);
    return () => window.removeEventListener("docintel-access", sync);
  }, []);
  return code;
}

export function Gate({ children }: { children: ReactNode }) {
  const code = useAccess();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (code === null) return;
    if (!code) { setChecked(true); return; }
    getJSON("/stats").then(() => setChecked(true)).catch((e) => {
      if (e instanceof ApiError && e.status === 401) { setCode(""); setError("That access code is not valid."); }
      setChecked(true);
    });
  }, [code]);

  if (code === null) return null;
  if (code) return <>{children}</>;   // shown at once; a wrong code is cleared by the background check
  if (!checked) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setCode(value.trim().replace(/^["“”']|["“”']$/g, ""));
    try { await getJSON("/stats"); } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setCode("");
        setError("That access code is not valid. Check it in the email and try again.");
      }
      // any other problem (server restarting, network): keep the code; the app shows a calm notice and retries
    } finally { setBusy(false); }
  }

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
      <form className="card card-pad stack" onSubmit={submit} style={{ width: "min(420px, 100%)", padding: 28 }}>
        <div className="big-ico" style={{ width: 48, height: 48, borderRadius: 14, background: "var(--brand-50)", color: "var(--brand)", display: "grid", placeItems: "center" }}>
          <KeyRound size={22} />
        </div>
        <h2>Enter the demo access code</h2>
        <p className="muted">The code is in the email that shared this demo. It protects the AI budget, and it is asked for again in every new browser session.</p>
        <input className="input" autoFocus placeholder="Access code" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Access code"
          autoComplete="off" autoCapitalize="none" spellCheck={false} />
        {error && <div className="notice err small">{error}</div>}
        <button className="btn btn-primary btn-lg" disabled={!value.trim() || busy}>{busy ? "Checking…" : "Open the demo"}</button>
        <p className="faint small">Documentation and the guide are open without a code.</p>
      </form>
    </div>
  );
}
