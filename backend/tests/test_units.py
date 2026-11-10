"""Unit tests: file detection, value cleaning, the evidence guard, validation rules, invoice splitting."""
from datetime import date
from decimal import Decimal

import pytest

from app.pipeline import evidence
from app.pipeline.detect import ProcessingError, detect
from app.pipeline.normalize import (normalize_currency, normalize_invoice_number, normalize_name, normalize_text,
                                    parse_amount, parse_date)
from app.pipeline.readers import Page
from app.pipeline.segment import find_invoice_number, split_invoices
from app.pipeline.types import ExtractedInvoice, FieldValue
from app.pipeline.validate import validate

from . import factories as F


# ------------------------------------------------------------------ detection
@pytest.mark.parametrize("name,data,expected", [
    ("a.pdf", b"%PDF-1.7\n...", "pdf"),
    ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image"),
    ("a.jpg", b"\xff\xd8\xff\xe0" + b"0" * 20, "image"),
    ("a.tiff", b"II*\x00" + b"0" * 20, "image"),
    ("a.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 20, "xls"),
    ("a.csv", b"Invoice,Total\nA-1,10.00\n", "csv"),
    ("renamed.jpg", b"%PDF-1.4 real pdf with a wrong name", "pdf"),
])
def test_detect_by_content(tmp_path, name, data, expected):
    p = tmp_path / name
    p.write_bytes(data)
    assert detect(p, name).file_type == expected


def test_detect_xlsx(tmp_path):
    p = tmp_path / "r.xlsx"
    p.write_bytes(F.xlsx_register([["A-1", "2026-01-01", "S", "C", 1, 0, 1, "USD"]]))
    assert detect(p, "r.xlsx").file_type == "xlsx"


@pytest.mark.parametrize("name,data,code", [
    ("empty.png", b"", "EMPTY_FILE"),
    ("fake.pdf", b"\x00\x01\x02 not a pdf" * 50, "CORRUPTED_FILE"),
    ("cut.xlsx", b"PK\x03\x04" + b"\x00" * 100, "CORRUPTED_FILE"),
    ("notes.docx", b"\x00\x01binary", "UNSUPPORTED_TYPE"),
])
def test_detect_rejects(tmp_path, name, data, code):
    p = tmp_path / name
    p.write_bytes(data)
    with pytest.raises(ProcessingError) as e:
        detect(p, name)
    assert e.value.code == code


# ------------------------------------------------------------------ normalisation
@pytest.mark.parametrize("raw,expected", [
    ("1,234.50", "1234.50"), ("1.234,50", "1234.50"), ("$ 99", "99"), ("(45.00)", "-45.00"),
    ("1234,56", "1234.56"), ("12,34,567", "1234567"), ("USD 2,000.00", "2000.00"), (115.5, "115.5"),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [None, "", "n/a", "abc", True])
def test_parse_amount_rejects(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize("raw,expected,ambiguous", [
    ("2026-03-14", date(2026, 3, 14), False), ("14/03/2026", date(2026, 3, 14), False),
    ("March 4, 2026", date(2026, 3, 4), False), ("14 Mar 2026", date(2026, 3, 14), False),
    ("03/04/2026", None, True),
])
def test_parse_date(raw, expected, ambiguous):
    d, amb = parse_date(raw)
    assert amb == ambiguous
    if expected:
        assert d == expected


def test_names_and_numbers():
    assert normalize_name("Northwind Medical Supplies Ltd.") == "northwind medical supplies"
    assert normalize_invoice_number("inv # 00-2041 ") == "INV002041"
    assert normalize_currency("$") == "USD" and normalize_currency("Tk") == "BDT" and normalize_currency("eur") == "EUR"
    assert normalize_currency("XYZ") is None


# ------------------------------------------------------------------ evidence guard
TEXT = normalize_text("INVOICE\nInvoice No: INV-2041\nSubtotal: 100.00\nTotal Due: USD 115.00")


def test_evidence_exact_and_value_inside():
    assert evidence.check(Decimal("115.00"), "Total Due: USD 115.00", TEXT, "amount") == (True, 1.0)
    assert evidence.check("INV-2041", "Invoice No: INV-2041", TEXT, "string")[0]
    assert evidence.check("USD", "USD 115.00", TEXT, "currency")[0]


def test_evidence_rejects_invented_values():
    # the quote is not in the document
    assert not evidence.check(Decimal("999.00"), "Total: 999.00", TEXT, "amount")[0]
    # the quote is real but the value is not inside it
    assert not evidence.check(Decimal("120.00"), "Total Due: USD 115.00", TEXT, "amount")[0]
    assert not evidence.check(None, None, TEXT, "string")[0]


def test_evidence_tolerates_small_ocr_differences():
    ocr = normalize_text("Invoice N0: INV-2041   Tota1 Due: USD 115.00")
    verified, strength = evidence.check("INV-2041", "Invoice No: INV-2041", ocr, "string")
    assert verified and 0.88 <= strength < 1.0


# ------------------------------------------------------------------ validation
def inv(**vals) -> ExtractedInvoice:
    base = {"invoice_number": "A-1", "invoice_date": date(2026, 3, 1), "supplier_name": "S", "customer_name": "C",
            "subtotal": Decimal("100.00"), "tax": Decimal("15.00"), "total": Decimal("115.00"), "currency": "USD"}
    base.update(vals)
    items = base.pop("items", [{"description": "x", "quantity": 2, "unit_price": 50, "amount": 100}])
    return ExtractedInvoice(fields={k: FieldValue(v, verified=True if v is not None else None, confidence=0.9)
                                    for k, v in base.items()}, line_items=items)


def codes(e):
    return sorted(i.code for i in validate(e, today=date(2026, 6, 1)))


def test_clean_invoice_has_no_issues():
    assert codes(inv()) == []


def test_total_mismatch():
    assert "TOTAL_MISMATCH" in codes(inv(total=Decimal("120.00")))


def test_rounding_is_tolerated():
    assert codes(inv(total=Decimal("115.01"))) == []


def test_line_item_math_and_sum():
    c = codes(inv(items=[{"description": "x", "quantity": 2, "unit_price": 50, "amount": 120}]))
    assert "LINE_ITEM_MATH" in c and "LINE_ITEMS_MISMATCH" in c


def test_missing_required_and_expected_fields():
    c = validate(inv(invoice_number=None, customer_name=None), today=date(2026, 6, 1))
    sev = {(i.code, i.field): i.severity for i in c}
    assert sev[("MISSING_FIELD", "invoice_number")] == "error"
    assert sev[("MISSING_FIELD", "customer_name")] == "warning"


def test_negative_and_future_and_unusual_tax():
    assert "INVALID_AMOUNT" in codes(inv(total=Decimal("-5"), subtotal=None, tax=None, items=[]))
    assert "FUTURE_DATE" in codes(inv(invoice_date=date(2027, 1, 1)))
    assert "UNUSUAL_TAX_RATE" in codes(inv(tax=Decimal("60.00"), total=Decimal("160.00")))


def test_unverified_value_is_reported_not_missing():
    e = inv()
    e.fields["total"] = FieldValue(None, evidence="Total: 999", verified=False)
    c = codes(e)
    assert "UNVERIFIED_VALUE" in c and ("MISSING_FIELD" not in c or all(
        i.field != "total" for i in validate(e) if i.code == "MISSING_FIELD"))


def test_spreadsheet_row_only_needs_its_columns():
    e = ExtractedInvoice(fields={"invoice_number": FieldValue("A-1", verified=True),
                                 "total": FieldValue(Decimal("10"), verified=True)}, source_kind="record")
    assert codes(e) == []


# ------------------------------------------------------------------ splitting
def page(n, text):
    return Page(page_no=n, text=text, method="digital")


def test_find_invoice_number_ignores_dates_and_labels():
    assert find_invoice_number("Invoice Date: 2026-03-14\nInvoice No: INV-77\n") == "INV-77"
    assert find_invoice_number("Bill To: Riverside Clinic") is None


def test_split_multi_invoice_batch():
    pages = [page(1, "Invoice No: A-1\nTotal 10"), page(2, "Invoice No: A-2\nitems Page 1 of 2"),
             page(3, "Invoice No: A-2\nPage 2 of 2 continued\nTotal 20"), page(4, "Invoice No: A-3\nTotal 5"),
             page(5, "terms and conditions")]
    segs = split_invoices(pages)
    assert [s.page_numbers for s in segs] == [[1], [2, 3], [4, 5]]
    assert [s.invoice_number for s in segs] == ["A-1", "A-2", "A-3"]


# ------------------------------------------------------------------ dual reading (scans)
from app.pipeline.extract import reconcile  # noqa: E402


def reading(**vals):
    items = vals.pop("items", [{"description": "x", "quantity": 2, "unit_price": 50, "amount": 100}])
    base = {"invoice_number": "A-1", "invoice_date": date(2026, 3, 1), "supplier_name": "S", "customer_name": "C",
            "subtotal": Decimal("100.00"), "tax": Decimal("15.00"), "total": Decimal("115.00"), "currency": "USD"}
    base.update(vals)
    return ExtractedInvoice(fields={k: FieldValue(v, evidence=str(v), verified=True, confidence=0.97) for k, v in base.items()},
                            line_items=items)


def test_two_readings_that_agree_are_confirmed():
    m = reconcile(reading(), reading())
    assert m.method == "llm_dual" and m.fields["total"].source == "vision+text"
    assert codes(m) == []


def test_amount_disagreement_is_settled_by_the_arithmetic():
    # OCR misread the total (175 instead of 115); the image reading adds up -> image value kept, no flag
    ocr = reading(total=Decimal("175.00"))
    ocr.fields["total"].confidence = 0.7
    m = reconcile(ocr, reading())
    assert m.get("total") == Decimal("115.00") and codes(m) == []


def test_line_item_misread_is_fixed_from_the_image():
    ocr = reading(items=[{"description": "x", "quantity": 3, "unit_price": 50, "amount": 100}])  # 3 read for 2
    m = reconcile(ocr, reading())
    assert m.line_items[0]["quantity"] == 2 and "LINE_ITEM_MATH" not in codes(m)


def test_unresolvable_disagreement_is_flagged_with_both_readings():
    img = reading(invoice_number="B-1")
    m = reconcile(reading(), img)
    issues = [i for i in validate(m, today=date(2026, 6, 1)) if i.code == "READINGS_DISAGREE"]
    assert issues and issues[0].details["ocr_text"] == "A-1" and issues[0].details["image"] == "B-1"


def test_complete_line_items_beat_an_empty_reading():
    no_items = reading(items=[])
    m = reconcile(no_items, reading())
    assert len(m.line_items) == 1 and m.line_items[0]["amount"] == 100


def test_items_without_amounts_do_not_win():
    blanks = reading(items=[{"description": "x", "quantity": None, "unit_price": None, "amount": None}])
    m = reconcile(reading(), blanks)
    assert m.line_items[0]["amount"] == 100
