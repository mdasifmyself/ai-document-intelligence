"""Writes frontend/lib/eval-summary.json and fills the measured numbers into README.md from the latest results."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ROOT / "evaluation/results"
ev = json.loads((R / "evaluation.json").read_text())
big = json.loads((R / "big-batch.json").read_text()) if (R / "big-batch.json").exists() else None
e, v, d, s = ev["extraction"], ev["validation"], ev["documents"], ev["speed"]
summary = {
    "run_at": ev["run_at"], "field_accuracy": e["overall_field_accuracy_pct"],
    "success_rate": d["success_rate_pct"], "broken_handled": d["broken_files_handled_pct"],
    "planted_caught": f"{v['planted_issues_caught']}/{v['planted_issues_total']}", "doc_ms_p50": s["doc_ms_p50"],
    "nulls_kept": e["missing_fields_left_empty_pct"],
}
big_text = "see the evaluation report"
if big:
    be, bs = big["extraction"], big["speed"]
    minutes = round(bs["wall_clock_seconds"] / 60, 1)
    summary.update({"big_pages": bs["pages"], "big_minutes": minutes, "big_invoices": be["invoices_found"]})
    big_text = (f"{bs['pages']:,} pages, {be['invoices_found']}/{be['invoices_expected']} invoices found, "
                f"{be['overall_field_accuracy_pct']} % field accuracy, {minutes} min")
(ROOT / "frontend/lib/eval-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
readme = (ROOT / "README.md").read_text()
fill = {
    "{{FIELD_ACC}}": f"{e['overall_field_accuracy_pct']} %", "{{ALL_FIELDS}}": f"{e['invoices_all_fields_correct_pct']} %",
    "{{FOUND}}": f"{e['invoices_found']} / {e['invoices_expected']}",
    "{{INVENTED}}": f"{sum(e['invented_values'].values())}", "{{PLANTED}}": summary["planted_caught"],
    "{{SUCCESS}}": f"{d['success_rate_pct']} %", "{{FAILURE}}": f"{d['failure_rate_pct']} %",
    "{{BROKEN}}": f"{d['broken_files_handled_pct']} % of {d['broken_files']}",
    "{{MEDIAN}}": f"{s['doc_ms_p50'] / 1000:.1f} s (scans ≈ 15 s: read twice)", "{{BIG}}": big_text,
}
for k, val in fill.items():
    readme = readme.replace(k, str(val))
(ROOT / "README.md").write_text(readme)
print(json.dumps(summary, indent=1))
