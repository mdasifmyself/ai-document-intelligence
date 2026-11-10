"""Failure scenarios: broken files, unsupported files, oversize uploads, AI outage and reprocessing."""
import io

import httpx
import pytest

from app.ai import client as ai_client
from app.config import get_settings

from . import factories as F


def up(client, *files):
    return client.post("/api/v1/documents", files=[("files", (n, io.BytesIO(d))) for n, d in files])


def status(client, doc_id):
    return client.get(f"/api/v1/documents/{doc_id}").json()


@pytest.mark.parametrize("name,data,code", [
    ("empty.png", b"", "EMPTY_FILE"),
    ("random.pdf", bytes(range(256)) * 20, "CORRUPTED_FILE"),
    ("text.jpg", b"just some text\n" * 30, "CORRUPTED_FILE"),
    ("locked.pdf", None, "PASSWORD_PROTECTED"),
    ("cut.xlsx", b"PK\x03\x04" + b"\x00" * 200, "CORRUPTED_FILE"),
])
def test_broken_files_fail_politely(client, name, data, code):
    if data is None:
        data = F.pdf(F.invoice(), password="secret")
    r = up(client, (name, data))
    assert r.status_code == 202
    d = status(client, r.json()["accepted"][0]["id"])
    assert d["status"] == "failed" and d["error_code"] == code
    assert d["error_message"] and d["issues"][0]["code"] == code


def test_unsupported_and_oversize_are_rejected_at_upload(client, monkeypatch):
    r = up(client, ("notes.docx", b"PK\x03\x04data"), ("ok.pdf", F.pdf(F.invoice())))
    body = r.json()
    assert [x["code"] for x in body["rejected"]] == ["UNSUPPORTED_TYPE"]
    assert len(body["accepted"]) == 1
    monkeypatch.setattr(get_settings(), "max_file_mb", 0)
    r = up(client, ("big.pdf", F.pdf(F.invoice())))
    assert r.json()["rejected"][0]["code"] == "FILE_TOO_LARGE"


def test_too_many_files_in_one_upload(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_files_per_upload", 2)
    r = up(client, *[(f"{i}.pdf", b"%PDF") for i in range(3)])
    assert r.status_code == 413


def test_ai_outage_then_reprocess(client, fake_ai):
    fake_ai.down = True
    r = up(client, ("a.pdf", F.pdf(F.invoice())))
    did = r.json()["accepted"][0]["id"]
    d = status(client, did)
    assert d["status"] == "failed" and d["error_code"] == "AI_UNAVAILABLE"
    failed = client.get("/api/v1/jobs/failed").json()
    assert failed["total"] == 1
    fake_ai.down = False
    rr = client.post("/api/v1/jobs/reprocess-failed").json()
    assert rr["requeued"] == 1
    d = status(client, did)
    assert d["status"] == "completed" and d["attempts"] == 2
    assert any(e["stage"] == "reprocess" for e in d["events"])


def test_single_reprocess_endpoint(client):
    r = up(client, ("a.pdf", F.pdf(F.invoice())))
    did = r.json()["accepted"][0]["id"]
    assert client.post(f"/api/v1/documents/{did}/reprocess").status_code == 200
    assert status(client, did)["attempts"] == 2


def test_ai_client_retries_then_succeeds(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ai_provider", "openai")
    monkeypatch.setattr(s, "ai_daily_call_limit", 0)
    monkeypatch.setattr(ai_client.time, "sleep", lambda *_: None)
    answers = iter([httpx.Response(503, text="busy"), httpx.Response(429, text="slow down"),
                    httpx.Response(200, json={"output_text": "{\"ok\": true}"})])
    monkeypatch.setattr(ai_client.httpx, "post", lambda *a, **k: next(answers))
    assert ai_client.call("responses", {"model": "m"}) == {"output_text": "{\"ok\": true}"}


def test_ai_client_gives_up_on_permanent_errors(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ai_provider", "openai")
    monkeypatch.setattr(s, "ai_daily_call_limit", 0)
    monkeypatch.setattr(ai_client.time, "sleep", lambda *_: None)
    calls = []
    monkeypatch.setattr(ai_client.httpx, "post", lambda *a, **k: calls.append(1) or httpx.Response(401, text="bad key"))
    with pytest.raises(ai_client.AIUnavailable):
        ai_client.call("responses", {"model": "m"})
    assert len(calls) == 1
