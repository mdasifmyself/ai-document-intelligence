"""Reading real files: digital PDF text, OCR for scans/photos/TIFF, spreadsheets, broken files."""
import pytest

from app.pipeline.detect import ProcessingError
from app.pipeline.ocr import ocr_image
from app.pipeline.readers import read_image, read_pdf
from app.pipeline.spreadsheets import match_header, read_spreadsheet

from . import factories as F


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_digital_pdf_uses_text_layer(tmp_path):
    pages = read_pdf(write(tmp_path, "a.pdf", F.pdf(F.invoice(), F.invoice(number="INV-1002"))))
    assert len(pages) == 2
    assert all(p.method == "digital" for p in pages)
    assert "INV-1002" in pages[1].text


def test_scanned_pdf_goes_to_ocr(tmp_path):
    pages = read_pdf(write(tmp_path, "s.pdf", F.scanned_pdf(F.invoice())))
    assert pages[0].method == "ocr"
    assert pages[0].ocr_confidence > 60
    assert "INV-1001" in pages[0].text.replace(" ", "")


def test_ocr_fixes_sideways_photo():
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(F.image(F.invoice(), sideways=True)))
    r = ocr_image(img)
    assert r.rotation in (90, 270)
    assert "Northwind" in r.text


def test_noisy_jpeg_and_multipage_tiff(tmp_path):
    pages = read_image(write(tmp_path, "p.jpg", F.image(F.invoice(), "JPEG", noisy=True)))
    assert "INV-1001" in pages[0].text.replace(" ", "")
    pages = read_image(write(tmp_path, "t.tiff", F.tiff(F.invoice(), F.invoice(number="INV-2002"))))
    assert len(pages) == 2 and "INV-2002" in pages[1].text.replace(" ", "")


def test_password_protected_pdf(tmp_path):
    with pytest.raises(ProcessingError) as e:
        read_pdf(write(tmp_path, "l.pdf", F.pdf(F.invoice(), password="x")))
    assert e.value.code == "PASSWORD_PROTECTED"


def test_damaged_image_is_read_with_warning(tmp_path):
    data = F.image(F.invoice(), "JPEG")
    pages = read_image(write(tmp_path, "cut.jpg", data[: int(len(data) * 0.8)]))
    assert pages[0].warnings


def test_header_matching():
    assert match_header("Invoice No.") == "invoice_number"
    assert match_header("Grand Total") == "total"
    assert match_header("VAT Amount") == "tax"
    assert match_header("Due Date") is None


def test_xlsx_register_with_line_items_and_extra_sheet(tmp_path):
    data = F.xlsx_register([["A-1", "2026-03-01", "Northwind", "Sunrise", 100, 15, 115, "USD"],
                            ["A-2", "2026-03-02", "Brightline", "Maple", 50, 0, 50, "USD"],
                            [None, None, None, None, None, None, 165, None]],
                           items=[["A-1", "Gloves", 2, 50, 100]])
    r = read_spreadsheet(write(tmp_path, "r.xlsx", data), "xlsx")
    assert [p.label for p in r.pages] == ["Invoices", "Line Items", "Notes"]
    assert len(r.records) == 2
    a1 = r.records[0]
    assert a1.get("total") == 115 and a1.line_items[0]["description"] == "Gloves"
    assert a1.fields["total"].evidence.startswith("Invoices!G2")


def test_xls_and_eu_csv(tmp_path):
    r = read_spreadsheet(write(tmp_path, "v.xls", F.xls_register([["B-1", "14/03/2026", "Meghna", "Lotus", 1000, 50, 1050, "BDT"]])), "xls")
    assert r.records[0].get("currency") == "BDT" and str(r.records[0].get("invoice_date")) == "2026-03-14"
    csv = "Invoice Number;Date;Supplier;Customer;Net;VAT;Total;Currency\nE-1;14.03.2026;Kestrel;Maple;1.234,50;246,90;1.481,40;EUR\n"
    r = read_spreadsheet(write(tmp_path, "e.csv", csv.encode()), "csv")
    assert float(r.records[0].get("total")) == 1481.40


def test_corrupted_spreadsheet(tmp_path):
    with pytest.raises(ProcessingError):
        read_spreadsheet(write(tmp_path, "x.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 300), "xls")
