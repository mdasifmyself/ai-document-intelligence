"""Operations: Excel export, automatic recovery of stuck jobs, failure callback, system status."""
import io
from datetime import datetime, timedelta, timezone

from openpyxl import load_workbook

from app.db import session_scope
from app.models import Document
from app.recovery import MAX_ATTEMPTS, STALE_MINUTES, on_job_failure, sweep

from . import factories as F


def up(client, *files):
    r = client.post("/api/v1/documents", files=[("files", (n, io.BytesIO(d))) for n, d in files])
    assert r.status_code == 202
    return r.json()["accepted"]


def test_excel_export_has_every_sheet_and_values(client):
    up(client, ("a.pdf", F.pdf(F.invoice(number="X-1"))), ("bad.pdf", F.pdf(F.invoice(number="X-2", total=999.0))))
    r = client.get("/api/v1/export.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Summary", "Invoices", "Line items", "Issues", "Cross-checks", "Documents"]
    inv = wb["Invoices"]
    header = [c.value for c in inv[1]]
    assert header[:8] == ["Invoice number", "Invoice date", "Supplier", "Customer", "Subtotal", "Tax", "Total", "Currency"]
    rows = {r[0]: r for r in inv.iter_rows(min_row=2, values_only=True)}
    assert rows["X-1"][6] == 230.0 and rows["X-2"][9] == "Needs review"
    assert "TOTAL_MISMATCH" in rows["X-2"][10]
    assert wb["Line items"].max_row == 5           # header + 2 lines per invoice
    assert any(r[2] == "TOTAL_MISMATCH" for r in wb["Issues"].iter_rows(min_row=2, values_only=True))


def test_excel_export_filtered(client):
    up(client, ("a.pdf", F.pdf(F.invoice(number="Y-1"))), ("bad.pdf", F.pdf(F.invoice(number="Y-2", total=999.0))))
    wb = load_workbook(io.BytesIO(client.get("/api/v1/export.xlsx", params={"needs_review": True}).content))
    numbers = [r[0] for r in wb["Invoices"].iter_rows(min_row=2, values_only=True)]
    assert numbers == ["Y-2"]
    assert "needs_review=True" in str(wb["Summary"]["B10"].value)


def _make_stuck(client, attempts: int):
    doc = up(client, ("a.pdf", F.pdf(F.invoice(number=f"S-{attempts}"))))[0]
    with session_scope() as s:
        d = s.get(Document, doc["id"])
        d.status, d.attempts = "processing", attempts
        d.heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES + 5)
    return doc["id"]


def test_stuck_document_is_requeued_automatically(client):
    doc_id = _make_stuck(client, attempts=1)
    result = sweep()
    assert result["requeued"] == 1
    d = client.get(f"/api/v1/documents/{doc_id}").json()
    assert d["status"] == "completed"                       # processed again (inline in tests)
    assert any(e["stage"] == "recovery" for e in d["events"])


def test_document_that_keeps_crashing_is_failed_not_looped(client):
    doc_id = _make_stuck(client, attempts=MAX_ATTEMPTS)
    assert sweep()["failed"] == 1
    d = client.get(f"/api/v1/documents/{doc_id}").json()
    assert d["status"] == "failed" and d["error_code"] == "WORKER_LOST"


def test_failure_callback_marks_timeout(client):
    doc = up(client, ("a.pdf", F.pdf(F.invoice())))[0]
    with session_scope() as s:
        s.get(Document, doc["id"]).status = "processing"

    class Job:
        args = [doc["id"]]

    class JobTimeoutException(Exception):
        pass
    on_job_failure(Job(), None, JobTimeoutException, JobTimeoutException(), None)
    d = client.get(f"/api/v1/documents/{doc['id']}").json()
    assert d["status"] == "failed" and d["error_code"] == "JOB_TIMEOUT"


def test_system_status(client):
    r = client.get("/api/v1/system/status")
    assert r.status_code == 200
    body = r.json()
    assert "queue" in body and "documents" in body and "recent_failures" in body["documents"]
