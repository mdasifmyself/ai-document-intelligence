"""Builds test files in memory: digital PDFs, scans, photos, TIFFs, spreadsheets, broken files."""
import io

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

BASE = {
    "number": "INV-1001", "date": "14 Mar 2026", "supplier": "Northwind Medical Supplies Ltd",
    "customer": "Sunrise Home Care LLC", "items": [("Nitrile gloves", 2, 50.00), ("Toner cartridge", 1, 100.00)],
    "tax": 30.00, "currency": "USD", "total": None,
}


def invoice(**over) -> dict:
    d = {**BASE, **over}
    sub = round(sum(q * u for _, q, u in d["items"]), 2)
    d.setdefault("subtotal", sub)
    if d.get("subtotal") is None:
        d["subtotal"] = sub
    if d["total"] is None:
        d["total"] = round(d["subtotal"] + (d["tax"] or 0), 2)
    return d


def draw(c: canvas.Canvas, inv: dict, page_label: str | None = None):
    y = 740
    lines = ["INVOICE", inv["supplier"], f"Invoice No: {inv['number']}"]
    if inv.get("date"):
        lines.append(f"Date: {inv['date']}")
    if inv.get("customer"):
        lines.append(f"Bill To: {inv['customer']}")
    lines.append("")
    for desc, q, u in inv["items"]:
        lines.append(f"{desc} {q} {u:,.2f} {inv.get('amount_override', {}).get(desc, q * u):,.2f}")
    lines.append(f"Subtotal: {inv['subtotal']:,.2f}")
    if inv.get("tax") is not None:
        lines.append(f"Tax: {inv['tax']:,.2f}")
    lines.append(f"Total Due: {inv['currency']} {inv['total']:,.2f}")
    c.setFont("Helvetica", 13)
    for line in lines:
        c.drawString(60, y, line)
        y -= 24
    if page_label:
        c.drawString(60, 40, page_label)
    c.showPage()


def pdf(*invoices: dict, password: str | None = None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER, encrypt=password)
    for inv in invoices:
        draw(c, inv)
    c.save()
    return buf.getvalue()


def render(pdf_bytes: bytes, dpi: int = 200) -> list[Image.Image]:
    doc = pdfium.PdfDocument(pdf_bytes)
    pages = [doc[i].render(scale=dpi / 72).to_pil().convert("L") for i in range(len(doc))]
    doc.close()
    return pages


def noisy(img: Image.Image, rotate: float = 1.5, noise: float = 8) -> Image.Image:
    img = img.rotate(rotate, expand=False, fillcolor=255)
    a = np.array(img).astype(np.float32) + np.random.default_rng(1).normal(0, noise, img.size[::-1])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))


def scanned_pdf(*invoices: dict) -> bytes:
    pages = [noisy(p) for p in render(pdf(*invoices))]
    b = io.BytesIO()
    pages[0].save(b, "PDF", save_all=True, append_images=pages[1:], resolution=200)
    return b.getvalue()


def image(inv: dict, fmt: str = "PNG", **kw) -> bytes:
    img = render(pdf(inv))[0]
    if kw.get("noisy"):
        img = noisy(img)
    if kw.get("sideways"):
        img = img.rotate(90, expand=True, fillcolor=255)
    b = io.BytesIO()
    img.save(b, fmt)
    return b.getvalue()


def tiff(*invoices: dict) -> bytes:
    pages = [render(pdf(inv))[0] for inv in invoices]
    b = io.BytesIO()
    pages[0].save(b, "TIFF", save_all=True, append_images=pages[1:], compression="tiff_lzw")
    return b.getvalue()


def xlsx_register(rows: list[list], items: list[list] | None = None, extra_sheet: bool = True) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoices"
    ws.append(["Invoice No", "Date", "Supplier", "Customer", "Subtotal", "VAT", "Total", "Currency"])
    for r in rows:
        ws.append(r)
    if items:
        li = wb.create_sheet("Line Items")
        li.append(["Invoice No", "Description", "Qty", "Unit Price", "Amount"])
        for r in items:
            li.append(r)
    if extra_sheet:
        s = wb.create_sheet("Notes")
        s.append(["Prepared by", "Accounts team"])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def xls_register(rows: list[list]) -> bytes:
    import xlwt
    book = xlwt.Workbook()
    sh = book.add_sheet("Register")
    for c, v in enumerate(["Bill No", "Date", "Vendor", "Client", "Net Amount", "Tax Amount", "Grand Total", "Curr"]):
        sh.write(0, c, v)
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            sh.write(r, c, v)
    b = io.BytesIO()
    book.save(b)
    return b.getvalue()
