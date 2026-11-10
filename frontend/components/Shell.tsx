"use client";
import { Activity, BookOpen, Code2, FileSearch, FileStack, FolderGit2, GitCompareArrows, LayoutDashboard, Menu, Search, ShieldCheck, Upload, Workflow, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { API_URL, getCode, getJSON, PREPARED_FOR, REPO_URL, Stats } from "@/lib/api";

const NAV = [
  { group: "Work", items: [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/upload", label: "Upload", icon: Upload },
    { href: "/documents", label: "Documents", icon: FileStack },
    { href: "/review", label: "Review queue", icon: ShieldCheck, badge: true },
    { href: "/search", label: "Search", icon: Search },
    { href: "/cross-checks", label: "Cross-checks", icon: GitCompareArrows },
  ] },
  { group: "Operations", items: [
    { href: "/system", label: "System health", icon: Activity },
  ] },
  { group: "Help", items: [
    { href: "/guide", label: "How to use", icon: BookOpen },
    { href: "/how-it-works", label: "How it works", icon: Workflow },
  ] },
];

export function Logo() {
  return (
    <span className="brand">
      <span className="brand-mark"><FileSearch size={17} strokeWidth={2} /></span>
      DocIntel
    </span>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [review, setReview] = useState<number | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const on = (e: Event) => {
      const ok = (e as CustomEvent<boolean>).detail;
      if (ok) { if (timer) clearTimeout(timer); setOffline(false); }
      else if (!timer) timer = setTimeout(() => { setOffline(true); timer = null; }, 1200);
    };
    window.addEventListener("docintel-health", on);
    return () => window.removeEventListener("docintel-health", on);
  }, []);

  useEffect(() => { setOpen(false); }, [path]);
  useEffect(() => {
    let alive = true;
    const load = () => getCode() && getJSON<Stats>("/stats").then((s) => alive && setReview(s.invoices.needs_review)).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    window.addEventListener("docintel-refresh", load);
    return () => { alive = false; clearInterval(t); window.removeEventListener("docintel-refresh", load); };
  }, []);

  const side = (
    <aside className={`side ${open ? "open" : ""}`} aria-label="Main navigation">
      <Link href="/" aria-label="DocIntel home"><Logo /></Link>
      {NAV.map((g) => (
        <nav className="nav" key={g.group}>
          <div className="nav-group">{g.group}</div>
          {g.items.map(({ href, label, icon: Icon, badge }) => (
            <Link key={href} href={href} className={path === href || path.startsWith(href + "/") ? "active" : ""}>
              <Icon size={18} strokeWidth={1.75} />
              {label}
              {badge && review ? <span className="count num">{review}</span> : null}
            </Link>
          ))}
        </nav>
      ))}
      <div className="side-foot">
        <a href={`${API_URL}/api/docs`} target="_blank" rel="noreferrer" className="row" style={{ gap: 8 }}><Code2 size={15} /> API reference</a>
        {REPO_URL && <a href={REPO_URL} target="_blank" rel="noreferrer" className="row" style={{ gap: 8 }}><FolderGit2 size={15} /> Source code</a>}
        <span>Built by Md Asif{PREPARED_FOR ? ` · Prepared for ${PREPARED_FOR}` : ""}</span>
      </div>
    </aside>
  );

  return (
    <div className="shell">
      {side}
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <div style={{ minWidth: 0 }}>
        <header className="topbar">
          <Link href="/"><Logo /></Link>
          <button className="btn icon-btn" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
        </header>
        {offline && (
          <div className="conn-banner" role="status"><span className="spinner" /> Reconnecting to the processing server… Your work is safe; this page continues by itself.</div>
        )}
        <main className="main">{children}</main>
      </div>
    </div>
  );
}
