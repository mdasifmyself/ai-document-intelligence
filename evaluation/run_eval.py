"""Measure the real system against the labelled dataset.

    python evaluation/run_eval.py --api https://<api-host> --code <access-code> --data dataset/out
    python evaluation/run_eval.py ... --big        # the 1,000-page batch PDF (speed + accuracy at scale)

Uploads every file through the public API, waits for the background workers, then compares each
extracted field with the answer key. Writes evaluation/results/<name>.json and <name>.md.
Nothing is estimated: every number in the report comes from this run.
"""
import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.pipeline.normalize import normalize_invoice_number, normalize_name  # noqa: E402

FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency")
REVIEW = {"error", "warning"}


def same(field, truth, pred) -> bool:
    if truth is None:
        return pred is None
    if pred is None:
        return False
    if field in ("subtotal", "tax", "total"):
        return abs(float(truth) - float(pred)) <= 0.011
    if field == "invoice_number":
        return normalize_invoice_number(truth) == normalize_invoice_number(pred)
    if field in ("supplier_name", "customer_name"):
        return fuzz.ratio(normalize_name(truth) or "", normalize_name(pred) or "") >= 90
    return str(truth) == str(pred)


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def pctl(values, q):
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo))


class Api:
    def __init__(self, base, code):
        self.c = httpx.Client(base_url=base.rstrip("/") + "/api/v1", headers={"X-Access-Code": code}, timeout=300)

    def upload(self, paths):
        files = [("files", (p.name, p.read_bytes())) for p in paths]
        r = self.c.post("/documents", files=files)
        r.raise_for_status()
        return r.json()

    def docs(self, ids):
        out = []
        for i in range(0, len(ids), 100):
            r = self.c.get("/documents", params={"ids": ",".join(ids[i:i + 100]), "page_size": 200})
            r.raise_for_status()
            out += r.json()["items"]
        return out

    def detail(self, doc_id):
        r = self.c.get(f"/documents/{doc_id}")
        r.raise_for_status()
        return r.json()


def wait(api, ids, timeout_s):
    t0 = time.time()
    while True:
        docs = api.docs(ids)
        busy = [d for d in docs if d["status"] in ("queued", "processing")]
        done = len(docs) - len(busy)
        print(f"\r  {done}/{len(ids)} finished ({int(time.time() - t0)} s)", end="", flush=True)
        if not busy:
            print()
            return time.time() - t0
        if time.time() - t0 > timeout_s:
            print("\n  timeout: some documents are still processing")
            return time.time() - t0
        time.sleep(4)


def match(truths, preds):
    """Pair expected invoices with extracted ones by invoice number, then by supplier + total."""
    pairs, left = [], list(preds)
    for t in truths:
        hit = next((p for p in left if t["invoice_number"] and same("invoice_number", t["invoice_number"], p["invoice_number"])), None)
        if hit is None:
            hit = next((p for p in left if p["total"] is not None and t["total"] is not None
                        and same("total", t["total"], p["total"]) and same("supplier_name", t["supplier_name"], p["supplier_name"])), None)
        if hit is not None:
            left.remove(hit)
        pairs.append((t, hit))
    return pairs, left


def evaluate(api, data: Path, labels: dict, batch: int, timeout_s: int, resume_id: str | None = None):
    files = sorted(labels)
    t0 = time.time()
    ids, name_of = [], {}
    if resume_id:  # measure a document that is already uploaded and processing
        d = api.detail(resume_id)
        ids, name_of = [resume_id], {resume_id: d["filename"]}
        wall = wait(api, ids, timeout_s)
        d = api.detail(resume_id)
        started = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
        wall = (d["processing_ms"] or 0) / 1000 or wall
        return {d["filename"]: d}, 0.0, wall
    for i in range(0, len(files), batch):
        res = api.upload([data / f for f in files[i:i + batch]])
        for d in res["accepted"]:
            ids.append(d["id"])
            name_of[d["id"]] = d["filename"]
        for r in res["rejected"]:
            print("  rejected at upload:", r)
    upload_s = time.time() - t0
    print(f"  uploaded {len(ids)} files in {upload_s:.1f} s")
    wall = wait(api, ids, timeout_s)
    details = {name_of[i]: api.detail(i) for i in ids}
    return details, upload_s, wall


def score(labels, details, upload_s, wall_s, model_info):
    field_ok, field_n = Counter(), Counter()
    null_ok, null_n = Counter(), Counter()
    halluc = Counter()
    kind_stats = defaultdict(lambda: {"files": 0, "fields_ok": 0, "fields_n": 0, "ms": []})
    found = missed = extra = exact = 0
    items_ok = items_n = 0
    issue_hit, issue_n = Counter(), Counter()
    false_flags = Counter()
    clean_invoices = clean_flagged = 0
    status_counts = Counter()
    expected_fail_ok = expected_fail_n = 0
    unexpected_failures = []
    per_doc_ms, per_page_ms, pages_total = [], [], 0
    methods = Counter()
    rows = []

    for name, lab in labels.items():
        d = details.get(name)
        if d is None:
            continue
        status_counts[d["status"]] += 1
        ks = kind_stats[lab["kind"]]
        ks["files"] += 1
        if d.get("processing_ms") is not None:
            ks["ms"].append(d["processing_ms"])
        if lab["expect_status"].startswith("failed"):
            expected_fail_n += 1
            graceful = d["status"] == "failed" or (lab["expect_status"] == "failed_or_flagged" and d["issues"])
            expected_fail_ok += bool(graceful)
            rows.append({"file": name, "kind": lab["kind"], "status": d["status"], "error": d["error_code"],
                         "expected_error": lab["expect_error"], "ok": bool(graceful)})
            continue
        if d["status"] == "failed":
            unexpected_failures.append({"file": name, "error": d["error_code"], "message": d["error_message"]})
        if d.get("processing_ms") is not None:
            per_doc_ms.append(d["processing_ms"])
            if d.get("page_count"):
                per_page_ms.append(d["processing_ms"] / d["page_count"])
                pages_total += d["page_count"]
        pairs, left = match(lab["invoices"], d["invoices"])
        extra += len(left)
        for t, p in pairs:
            if p is None:
                missed += 1
                rows.append({"file": name, "kind": lab["kind"], "invoice": t["invoice_number"], "wrong_fields": ["(not found)"],
                             "expected_issues": t.get("expect_issues", []), "got_issues": [], "status": d["status"]})
                for f in FIELDS:
                    field_n[f] += 1
                continue
            found += 1
            methods[p["extraction_method"]] += 1
            all_ok = True
            for f in FIELDS:
                if f not in t:
                    continue
                ok = same(f, t[f], p[f])
                field_n[f] += 1
                field_ok[f] += ok
                ks["fields_n"] += 1
                ks["fields_ok"] += ok
                all_ok &= ok
                if t[f] is None:
                    null_n[f] += 1
                    null_ok[f] += p[f] is None
                    halluc[f] += p[f] is not None
            exact += all_ok
            if "line_items" in t and t["line_items"]:
                items_n += 1
                got = sorted(round(float(i["amount"] or 0), 2) for i in p["line_items"])
                want = sorted(round(float(i["amount"]), 2) for i in t["line_items"])
                items_ok += got == want
            codes = {i["code"] for i in p["issues"]}
            review_codes = {i["code"] for i in p["issues"] if i["severity"] in REVIEW}
            expected = set(t.get("expect_issues", []))
            for code in expected:
                issue_n[code] += 1
                issue_hit[code] += code in codes
            if not (expected - {"LEDGER_MATCH"}):
                clean_invoices += 1
                if review_codes:
                    clean_flagged += 1
                    for c in review_codes:
                        false_flags[c] += 1
            rows.append({"file": name, "kind": lab["kind"], "invoice": t["invoice_number"],
                         "wrong_fields": [f for f in FIELDS if f in t and not same(f, t[f], p[f])],
                         "expected_issues": sorted(expected), "got_issues": sorted(codes), "status": d["status"]})

    valid = sum(1 for n, l in labels.items() if not l["expect_status"].startswith("failed") and n in details)
    processed_valid = valid - len(unexpected_failures)
    total_fields = sum(field_n.values())
    return {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models": model_info,
        "files": len(details),
        "documents": {
            "valid_files": valid, "processed": processed_valid, "unexpected_failures": unexpected_failures,
            "success_rate_pct": pct(processed_valid, valid), "failure_rate_pct": pct(len(unexpected_failures), valid),
            "broken_files": expected_fail_n, "broken_files_handled_pct": pct(expected_fail_ok, expected_fail_n),
            "status_counts": dict(status_counts),
        },
        "extraction": {
            "invoices_expected": found + missed, "invoices_found": found, "invoices_missed": missed,
            "extra_invoices": extra, "detection_rate_pct": pct(found, found + missed),
            "field_accuracy_pct": {f: pct(field_ok[f], field_n[f]) for f in FIELDS},
            "overall_field_accuracy_pct": pct(sum(field_ok.values()), total_fields),
            "invoices_all_fields_correct_pct": pct(exact, found + missed),
            "line_items_exact_pct": pct(items_ok, items_n),
            "missing_fields_left_empty_pct": pct(sum(null_ok.values()), sum(null_n.values())),
            "invented_values": dict(halluc), "methods": dict(methods),
        },
        "validation": {
            "planted_issue_detection_pct": {c: pct(issue_hit[c], issue_n[c]) for c in sorted(issue_n)},
            "planted_issues_total": sum(issue_n.values()), "planted_issues_caught": sum(issue_hit.values()),
            "clean_invoices": clean_invoices, "clean_invoices_flagged": clean_flagged,
            "false_flag_rate_pct": pct(clean_flagged, clean_invoices), "false_flag_codes": dict(false_flags),
        },
        "speed": {
            "upload_seconds": round(upload_s, 1), "wall_clock_seconds": round(wall_s, 1),
            "pages": pages_total, "doc_ms_p50": pctl(per_doc_ms, 0.5), "doc_ms_p95": pctl(per_doc_ms, 0.95),
            "doc_ms_max": max(per_doc_ms) if per_doc_ms else None,
            "page_ms_p50": pctl(per_page_ms, 0.5),
            "documents_per_minute": round(60 * len(details) / wall_s, 1) if wall_s else None,
            "pages_per_minute": round(60 * pages_total / wall_s, 1) if wall_s else None,
        },
        "by_kind": {k: {"files": v["files"], "field_accuracy_pct": pct(v["fields_ok"], v["fields_n"]),
                        "median_ms": pctl(v["ms"], 0.5)} for k, v in sorted(kind_stats.items())},
        "rows": rows,
    }


def markdown(r: dict, title: str) -> str:
    d, e, v, s = r["documents"], r["extraction"], r["validation"], r["speed"]
    L = [f"# {title}", "", f"Run: {r['run_at']} · models: {r['models']}", "",
         "| Metric | Result |", "|---|---|",
         f"| Files processed | {r['files']} |",
         f"| Document success rate (valid files) | {d['success_rate_pct']}% ({d['processed']}/{d['valid_files']}) |",
         f"| Document failure rate (valid files) | {d['failure_rate_pct']}% |",
         f"| Broken/locked files handled politely | {d['broken_files_handled_pct']}% of {d['broken_files']} |",
         f"| Invoices found | {e['invoices_found']}/{e['invoices_expected']} ({e['detection_rate_pct']}%) |",
         f"| Field accuracy (all fields) | **{e['overall_field_accuracy_pct']}%** |",
         f"| Invoices with every field correct | {e['invoices_all_fields_correct_pct']}% |",
         f"| Line items exactly right | {e['line_items_exact_pct']}% |",
         f"| Missing values left empty (not invented) | {e['missing_fields_left_empty_pct']}% |",
         f"| Planted problems caught | {v['planted_issues_caught']}/{v['planted_issues_total']} |",
         f"| Clean invoices wrongly flagged | {v['false_flag_rate_pct']}% ({v['clean_invoices_flagged']}/{v['clean_invoices']}) |",
         f"| Time per document (median / p95) | {s['doc_ms_p50']} ms / {s['doc_ms_p95']} ms |",
         f"| Throughput | {s['documents_per_minute']} documents/min · {s['pages_per_minute']} pages/min |",
         "", "## Field accuracy", "", "| Field | Accuracy |", "|---|---|"]
    L += [f"| {k} | {val}% |" for k, val in e["field_accuracy_pct"].items()]
    L += ["", "## By file type", "", "| Kind | Files | Field accuracy | Median time |", "|---|---|---|---|"]
    L += [f"| {k} | {x['files']} | {x['field_accuracy_pct']}% | {x['median_ms']} ms |" for k, x in r["by_kind"].items()]
    L += ["", "## Planted problems", "", "| Problem | Caught |", "|---|---|"]
    L += [f"| {k} | {val}% |" for k, val in v["planted_issue_detection_pct"].items()]
    if v["false_flag_codes"]:
        L += ["", "False flags on clean invoices: " + ", ".join(f"{k} ×{n}" for k, n in v["false_flag_codes"].items())]
    if d["unexpected_failures"]:
        L += ["", "Unexpected failures: " + "; ".join(f"{x['file']} ({x['error']})" for x in d["unexpected_failures"])]
    wrong = [x for x in r["rows"] if x.get("wrong_fields")]
    if wrong:
        L += ["", "## Every wrong field", "", "| File | Invoice | Wrong fields |", "|---|---|---|"]
        L += [f"| {x['file']} | {x['invoice']} | {', '.join(x['wrong_fields'])} |" for x in wrong]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--code", required=True)
    ap.add_argument("--data", default="dataset/out")
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--big", action="store_true")
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--resume-id", help="document id already uploaded (big batch): only wait and score")
    a = ap.parse_args()
    api = Api(a.api, a.code)
    meta = api.c.get("/meta").json()
    models = f"{meta['extraction_model']} (text), {meta['vision_model']} (vision), {meta['embedding_model']} (search)"
    data = Path(a.data)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.big:
        big = json.loads((data / "big" / "big_labels.json").read_text())
        labels = {"big_batch_1000_pages.pdf": {"kind": "pdf_big_batch", "expect_status": "processed",
                                               "invoices": big["invoices"]}}
        details, up_s, wall = evaluate(api, data / "big", labels, 1, a.timeout, a.resume_id)
        name, title = "big-batch", "DocIntel evaluation: 1,000-page batch PDF"
    else:
        labels = json.loads((data / "labels.json").read_text())["files"]
        details, up_s, wall = evaluate(api, data, labels, a.batch, a.timeout)
        name, title = "evaluation", "DocIntel evaluation: labelled dataset"
    r = score(labels, details, up_s, wall, models)
    (out / f"{name}.json").write_text(json.dumps(r, indent=1))
    (out / f"{name}.md").write_text(markdown(r, title))
    print(markdown(r, title))


if __name__ == "__main__":
    main()
