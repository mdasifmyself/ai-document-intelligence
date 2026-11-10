"""Test setup: a separate test database, a deterministic fake AI, inline (synchronous) jobs."""
import hashlib
import math
import os
import re
import tempfile

import pytest

os.environ["AI_PROVIDER"] = "fake"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or \
    "postgresql+psycopg://docintel:docintel@localhost:5432/docintel_test"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="docintel-test-")
os.environ["SAMPLES_DIR"] = tempfile.mkdtemp(prefix="docintel-samples-")
os.environ["ACCESS_CODES"] = "test-code"
os.environ["AI_CONCURRENCY"] = "2"
os.environ["UPLOADS_PER_MINUTE"] = "10000"

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.ai import client as ai_client  # noqa: E402
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


def _ensure_database():
    url = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        if not c.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}):
            c.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


_ensure_database()

from app import db as app_db  # noqa: E402
from app.queue import set_sync_mode  # noqa: E402

app_db.init_db()
set_sync_mode(True)


# ------------------------------------------------------------------ fake AI
def _line(text, pattern):
    m = re.search(pattern, text, re.I | re.M)
    return m


def fake_extract(text: str) -> dict:
    """Reads the simple test layout with regular expressions and answers in the model's JSON shape."""
    def field(pattern, group=1, number=False):
        m = _line(text, pattern)
        if not m:
            return {"value": None, "evidence": None}
        v = m.group(group).strip()
        if number:
            v = float(v.replace(",", ""))
        return {"value": v, "evidence": m.group(0).strip()}

    date = _line(text, r"^Date:\s*(.+)$")
    items = []
    for m in re.finditer(r"^(?P<d>[A-Za-z][A-Za-z ,]+?)\s+(?P<q>\d+)\s+(?P<u>[\d,]+\.\d\d)\s+(?P<a>[\d,]+\.\d\d)$", text, re.M):
        items.append({"description": m.group("d").strip(), "quantity": float(m.group("q")),
                      "unit_price": float(m.group("u").replace(",", "")),
                      "amount": float(m.group("a").replace(",", "")), "evidence": m.group(0)})
    cur = _line(text, r"^Total(?: Due)?:?\s*([A-Z]{3}|\$)")
    supplier = _line(text, r"^INVOICE\s*\n+(.+)$")
    return {
        "document_kind": "invoice" if re.search(r"invoice", text, re.I) else "other",
        "invoice_number": field(r"^Invoice No:\s*(\S+)"),
        "invoice_date": {"value": None, "raw": date.group(1).strip() if date else None,
                         "evidence": date.group(0).strip() if date else None},
        "supplier_name": {"value": supplier.group(1).strip(), "evidence": supplier.group(1).strip()} if supplier
        else {"value": None, "evidence": None},
        "customer_name": field(r"^Bill To:\s*(.+)$"),
        "subtotal": field(r"^Subtotal:?\s*([\d,]+\.\d\d)", number=True),
        "tax": field(r"^Tax:?\s*([\d,]+\.\d\d)", number=True),
        "total": field(r"^Total(?: Due)?:?\s*(?:[A-Z]{3}|\$)?\s*([\d,]+\.\d\d)", number=True),
        "currency": {"value": ("USD" if cur.group(1) == "$" else cur.group(1)), "evidence": cur.group(0)} if cur
        else {"value": None, "evidence": None},
        "line_items": items,
        "notes": None,
    }


def fake_embedding(text: str, dim: int = 1536) -> list[float]:
    v = [0.0] * dim
    for word in re.findall(r"[a-z]+", text.lower()):
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class FakeAI:
    def __init__(self):
        self.calls = []
        self.down = False
        self.override = None   # function(text) -> dict, to simulate a model that invents values

    def __call__(self, op, payload):
        self.calls.append(op)
        if self.down:
            raise ai_client.AIUnavailable("simulated outage")
        if op == "embeddings":
            return {"data": [{"index": i, "embedding": fake_embedding(t)} for i, t in enumerate(payload["input"])]}
        content = payload["input"][1]["content"]
        text = content if isinstance(content, str) else " ".join(c.get("text", "") for c in content if c.get("type") == "input_text")
        data = self.override(text) if self.override else fake_extract(text)
        import json
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(data)}]}]}


@pytest.fixture
def fake_ai():
    f = FakeAI()
    ai_client.set_fake_handler(f)
    yield f
    ai_client.set_fake_handler(None)


@pytest.fixture
def clean_db():
    with app_db.engine().begin() as c:
        c.execute(text("TRUNCATE cross_checks, corrections, validation_issues, invoices, document_pages, "
                       "processing_events, documents CASCADE"))
    yield


@pytest.fixture
def client(fake_ai, clean_db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        c.headers.update({"X-Access-Code": "test-code"})
        yield c
