"""End-to-end through the REST API: upload -> background job -> results -> corrections -> search."""
import io

from . import factories as F


def up(client, *files):
    r = client.post("/api/v1/documents", files=[("files", (n, io.BytesIO(d))) for n, d in files])
    assert r.status_code == 202, r.text
    return r.json()


def doc(client, doc_id):
    r = client.get(f"/api/v1/documents/{doc_id}")
    assert r.status_code == 200
    return r.json()


def issue_codes(d):
    return sorted({i["code"] for inv in d["invoices"] for i in inv["issues"]} | {i["code"] for i in d["issues"]})


def test_auth_is_required(client):
    r = client.get("/api/v1/documents", headers={"X-Access-Code": "wrong"})
    assert r.status_code == 401
    assert client.get("/api/v1/health").json()["status"] in ("ok", "degraded")


def test_upload_digital_pdf_end_to_end(client):
    res = up(client, ("inv.pdf", F.pdf(F.invoice())))
    d = doc(client, res["accepted"][0]["id"])
    assert d["status"] == "completed", issue_codes(d)
    assert d["text_method"] == "digital" and d["invoice_count"] == 1
    inv = d["invoices"][0]
    assert inv["invoice_number"] == "INV-1001"
    assert inv["invoice_date"] == "2026-03-14"
    assert inv["total"] == 230.0 and inv["currency"] == "USD"
    assert inv["fields"]["total"]["verified"] is True and inv["fields"]["total"]["evidence"]
    stages = [e["stage"] for e in d["events"] if e["status"] == "completed"]
    for s in ("detect", "read", "split", "extract", "validate", "match", "index"):
        assert s in stages
    status = client.get(f"/api/v1/documents/{d['id']}/status").json()
    assert status["status"] == "completed" and status["processing_ms"] >= 0


def test_scanned_and_photo_and_spreadsheet(client):
    res = up(client, ("scan.pdf", F.scanned_pdf(F.invoice(number="INV-3001"))),
             ("photo.jpg", F.image(F.invoice(number="INV-3002"), "JPEG", noisy=True)),
             ("ledger.xlsx", F.xlsx_register([["L-1", "2026-03-01", "Northwind", "Sunrise", 100, 15, 115, "USD"]])),
             ("export.csv", b"Invoice Number,Date,Supplier,Total,Currency\nC-1,2026-03-05,Apex,99.00,USD\n"))
    by_name = {a["filename"]: doc(client, a["id"]) for a in res["accepted"]}
    assert by_name["scan.pdf"]["text_method"] == "ocr"
    assert by_name["scan.pdf"]["invoices"][0]["invoice_number"] == "INV-3001"
    assert by_name["photo.jpg"]["invoices"][0]["total"] == 230.0
    assert by_name["ledger.xlsx"]["invoices"][0]["extraction_method"] == "spreadsheet_columns"
    assert by_name["export.csv"]["invoices"][0]["total"] == 99.0


def test_validation_flags_and_review_queue(client):
    bad = F.invoice(number="INV-4001", total=999.00)
    res = up(client, ("bad.pdf", F.pdf(bad)))
    d = doc(client, res["accepted"][0]["id"])
    assert d["status"] == "needs_review"
    assert "TOTAL_MISMATCH" in issue_codes(d)
    queue = client.get("/api/v1/invoices", params={"needs_review": True}).json()
    assert queue["total"] == 1


def test_missing_fields_are_null_not_invented(client):
    res = up(client, ("nodate.pdf", F.pdf(F.invoice(number="INV-5001", date=None, customer=None))))
    inv = doc(client, res["accepted"][0]["id"])["invoices"][0]
    assert inv["invoice_date"] is None and inv["customer_name"] is None
    codes = {i["code"] + ":" + (i["field"] or "") for i in inv["issues"]}
    assert "MISSING_FIELD:invoice_date" in codes and "MISSING_FIELD:customer_name" in codes


def test_model_inventing_a_value_is_blocked(client, fake_ai):
    from .conftest import fake_extract

    def liar(text):
        d = fake_extract(text)
        d["total"] = {"value": 5000.0, "evidence": "Total: 5,000.00"}       # not in the document
        d["customer_name"] = {"value": "Invented Corp", "evidence": None}  # no proof at all
        return d
    fake_ai.override = liar
    res = up(client, ("x.pdf", F.pdf(F.invoice(number="INV-6001"))))
    inv = doc(client, res["accepted"][0]["id"])["invoices"][0]
    assert inv["total"] is None and inv["customer_name"] is None
    assert inv["fields"]["total"]["verified"] is False
    assert "UNVERIFIED_VALUE" in {i["code"] for i in inv["issues"]}


def test_duplicates_and_cross_checks(client):
    data = F.pdf(F.invoice(number="INV-7001"))
    up(client, ("first.pdf", data))
    d2 = doc(client, up(client, ("again.pdf", data))["accepted"][0]["id"])   # byte-identical file
    assert "DUPLICATE_INVOICE" in issue_codes(d2)
    assert "DUPLICATE_FILE" in issue_codes(d2)
    # ledger row with a different total -> PDF vs Excel mismatch; matching row -> confirmed
    ledger = F.xlsx_register([["INV-7001", "2026-03-14", "Northwind Medical Supplies Ltd", "Sunrise Home Care LLC",
                               200, 30, 250, "USD"]])
    d3 = doc(client, up(client, ("ledger.xlsx", ledger))["accepted"][0]["id"])
    assert "CROSS_CHECK_MISMATCH" in issue_codes(d3)
    checks = client.get("/api/v1/cross-checks").json()
    kinds = {(c["kind"], c["status"]) for c in checks}
    assert ("pdf_pdf", "duplicate") in kinds and ("pdf_excel", "mismatch") in kinds


def test_batch_pdf_is_split_into_invoices(client):
    res = up(client, ("batch.pdf", F.pdf(F.invoice(number="B-1"), F.invoice(number="B-2"), F.invoice(number="B-3"))))
    d = doc(client, res["accepted"][0]["id"])
    assert [i["invoice_number"] for i in d["invoices"]] == ["B-1", "B-2", "B-3"]
    assert d["invoices"][1]["location"]["pages"] == [2]


def test_manual_correction_revalidates_and_keeps_history(client):
    res = up(client, ("bad.pdf", F.pdf(F.invoice(number="INV-8001", total=999.00))))
    inv = doc(client, res["accepted"][0]["id"])["invoices"][0]
    r = client.patch(f"/api/v1/invoices/{inv['id']}", json={"fields": {"total": "230.00"}, "reason": "Typo on invoice",
                                                             "corrected_by": "Asif"})
    assert r.status_code == 200, r.text
    fixed = r.json()
    assert fixed["total"] == 230.0 and "TOTAL_MISMATCH" not in {i["code"] for i in fixed["issues"]}
    assert fixed["corrections"][0]["old_value"] == 999.0 and fixed["corrections"][0]["corrected_by"] == "Asif"
    assert fixed["fields"]["total"]["source"] == "manual"
    a = client.post(f"/api/v1/invoices/{inv['id']}/approve", params={"reviewer": "Asif"}).json()
    assert a["status"] == "reviewed" and a["needs_review"] is False
    assert client.get(f"/api/v1/documents/{inv['document_id']}").json()["status"] == "completed"


def test_correction_rejects_bad_values(client):
    res = up(client, ("a.pdf", F.pdf(F.invoice(number="INV-8101"))))
    inv = doc(client, res["accepted"][0]["id"])["invoices"][0]
    assert client.patch(f"/api/v1/invoices/{inv['id']}", json={"fields": {"total": "abc"}}).status_code == 422
    assert client.patch(f"/api/v1/invoices/{inv['id']}", json={"fields": {"password": "x"}}).status_code == 422


def test_search_keyword_semantic_and_filters(client):
    up(client, ("a.pdf", F.pdf(F.invoice(number="S-1", supplier="Apex Cleaning Services",
                                       items=[("Deep cleaning per room", 3, 80.0)], tax=0))),
       ("b.pdf", F.pdf(F.invoice(number="S-2", supplier="BluePeak IT Solutions",
                                 items=[("Monthly IT support", 1, 900.0)], tax=0))))
    kw = client.get("/api/v1/search", params={"q": "cleaning", "mode": "keyword"}).json()
    assert kw["hits"][0]["invoice"]["invoice_number"] == "S-1"
    sem = client.get("/api/v1/search", params={"q": "IT support", "mode": "semantic"}).json()
    assert sem["hits"][0]["invoice"]["invoice_number"] == "S-2"
    hy = client.get("/api/v1/search", params={"q": "cleaning", "mode": "hybrid", "min_total": 100}).json()
    assert {h["invoice"]["invoice_number"] for h in hy["hits"]} == {"S-1"}
    docs = client.get("/api/v1/documents", params={"q": "BluePeak"}).json()
    assert docs["total"] == 1
    typo = client.get("/api/v1/search", params={"q": "Blupeak", "mode": "keyword"}).json()   # typo still finds it
    assert typo["hits"] and typo["hits"][0]["invoice"]["invoice_number"] == "S-2"


def test_page_text_image_file_and_delete(client):
    res = up(client, ("a.pdf", F.pdf(F.invoice())))
    did = res["accepted"][0]["id"]
    assert "INV-1001" in client.get(f"/api/v1/documents/{did}/pages/1").json()["text"]
    img = client.get(f"/api/v1/documents/{did}/pages/1/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get(f"/api/v1/documents/{did}/file").content.startswith(b"%PDF")
    assert client.delete(f"/api/v1/documents/{did}").status_code == 204
    assert client.get(f"/api/v1/documents/{did}").status_code == 404


def test_stats_and_meta(client):
    up(client, ("a.pdf", F.pdf(F.invoice())), ("broken.pdf", b"%PDF-1.4 broken"))
    s = client.get("/api/v1/stats").json()
    assert s["documents"]["total"] == 2 and s["invoices"]["total"] == 1
    assert 0 < s["documents"]["success_rate"] < 1
    m = client.get("/api/v1/meta").json()
    assert ".tiff" in m["allowed_extensions"] and m["access_code_required"] is True
