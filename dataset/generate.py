"""Generate the labelled evaluation dataset (fictional companies, deterministic: seed 42).

    python dataset/generate.py --out dataset/out            # evaluation set + answer key (labels.json)
    python dataset/generate.py --out dataset/out --big      # also the 1,000-page batch PDF for the speed test

Every file has a known correct answer. Problems are planted on purpose so the evaluation can measure
whether the system catches them: wrong totals, line items that don't add up, missing fields, ambiguous
dates, duplicates, conflicting copies, PDF-vs-Excel differences, corrupted and locked files, poor scans.
All names are invented; any resemblance to real businesses is accidental.
"""
import argparse
import io
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfgen import canvas

R = random.Random(42)

SUPPLIERS = [
    ("Northwind Medical Supplies Ltd", "18 Harbor Road, Chattogram"),
    ("Brightline Office Co.", "240 Lake Avenue, Newark, NJ"),
    ("Delta Care Pharmacy LLC", "77 Elm Street, Freehold, NJ"),
    ("Meghna Packaging Ltd", "Plot 12, Tongi I/A, Gazipur"),
    ("Harbor Linen Services", "5 Dock Lane, Baltimore, MD"),
    ("BluePeak IT Solutions", "Level 6, 31 Gulshan Ave, Dhaka"),
    ("Green Valley Foods Inc", "902 Route 9, Albany, NY"),
    ("Apex Cleaning Services", "61 Pine Street, Hartford, CT"),
    ("Silverline Logistics Ltd", "House 4, Road 11, Banani, Dhaka"),
    ("Kestrel Print & Design", "14 Market Row, Leeds"),
    ("Orchid Home Health Supply", "3300 Coral Way, Miami, FL"),
    ("Riverbend Electrical Co.", "88 Mill Road, Dearborn, MI"),
]
CUSTOMERS = ["Sunrise Home Care LLC", "Maple Senior Living", "Riverside Family Clinic", "Lotus Day Care Centre",
             "Cedar Grove Assisted Living", "Bayview Rehab Center", "Harmony Care Services"]
ITEMS = [("Nitrile gloves, box of 100", 6, 18), ("Adult briefs, pack of 20", 12, 32), ("Blood pressure monitor", 25, 90),
         ("Office chair, ergonomic", 85, 240), ("A4 copy paper, 5 reams", 18, 35), ("Toner cartridge", 45, 120),
         ("Bed linen set", 22, 60), ("Laundry service, per kg", 1, 3), ("Deep cleaning, per room", 35, 80),
         ("Monthly IT support", 300, 900), ("Laptop repair", 60, 220), ("Hand sanitizer 1L", 5, 12),
         ("Wheelchair rental, weekly", 40, 95), ("Delivery charge", 10, 45), ("Printed brochures, 500 pcs", 70, 180),
         ("Fresh produce delivery", 120, 400), ("Electrical inspection", 150, 380), ("LED panel light", 18, 55)]
TAX_RATES = [0, 5, 7.5, 10, 15]


@dataclass
class Inv:
    number: str
    date: date
    supplier: str
    supplier_addr: str
    customer: str | None
    currency: str
    items: list
    tax_rate: float
    subtotal: float
    tax: float
    total: float
    layout: str = "A"
    show_date: bool = True
    show_tax: bool = True
    date_text: str | None = None
    ambiguous_date: bool = False
    long: bool = False
    expect_issues: list = field(default_factory=list)

    def truth(self) -> dict:
        return {
            "invoice_number": self.number,
            "invoice_date": None if (not self.show_date or self.ambiguous_date) else self.date.isoformat(),
            "supplier_name": self.supplier, "customer_name": self.customer,
            "subtotal": self.subtotal, "tax": self.tax if self.show_tax else None, "total": self.total,
            "currency": self.currency,
            "line_items": [{"description": d, "quantity": q, "unit_price": u, "amount": a} for d, q, u, a in self.items],
            "expect_issues": sorted(set(self.expect_issues)),
        }


def money(x: float, eu=False) -> str:
    s = f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if eu else s


def new_invoice(i: int, layout: str, currency: str | None = None, n_items: int | None = None) -> Inv:
    sup, addr = R.choice(SUPPLIERS)
    cur = currency or R.choice(["USD"] * 5 + ["EUR", "GBP", "BDT"])
    k = n_items or R.randint(1, 6)
    items = []
    picks = R.sample(ITEMS, k) if k <= len(ITEMS) else [R.choice(ITEMS) for _ in range(k)]
    for desc, lo, hi in picks:
        q = R.choice([1, 1, 2, 3, 4, 5, 10, 12])
        u = round(R.uniform(lo, hi), 2)
        if cur == "BDT":
            u = round(u * 110, 2)
        items.append((desc, q, u, round(q * u, 2)))
    subtotal = round(sum(a for *_, a in items), 2)
    rate = R.choice(TAX_RATES)
    tax = round(subtotal * rate / 100, 2)
    prefix = {"A": "INV", "B": "BL", "C": "TX"}[layout]
    return Inv(number=f"{prefix}-{2026}{i:04d}", date=date(2026, 1, 5) + timedelta(days=R.randint(0, 120)),
               supplier=sup, supplier_addr=addr, customer=R.choice(CUSTOMERS), currency=cur, items=items,
               tax_rate=rate, subtotal=subtotal, tax=tax, total=round(subtotal + tax, 2), layout=layout)


def date_text(inv: Inv) -> str:
    if inv.date_text:
        return inv.date_text
    d = inv.date
    return {"A": d.strftime("%d %b %Y"), "B": d.strftime("%B %d, %Y").replace(" 0", " "),
            "C": d.strftime("%d/%m/%Y") if d.day > 12 else d.strftime("%d-%b-%Y")}[inv.layout]


def cur_label(inv: Inv) -> str:
    if inv.layout == "B" and inv.currency == "USD":
        return "$"
    return inv.currency


# ---------------------------------------------------------------- PDF drawing
def draw_invoice(c: canvas.Canvas, inv: Inv):
    w, h = c._pagesize
    rows_per_page = 18
    chunks = [inv.items[i:i + rows_per_page] for i in range(0, len(inv.items), rows_per_page)] or [[]]
    pages = len(chunks)
    for pi, chunk in enumerate(chunks):
        y = h - 60
        if inv.layout == "A":
            c.setFont("Helvetica-Bold", 22); c.drawString(50, y, "INVOICE")
            c.setFont("Helvetica-Bold", 11); c.drawString(50, y - 30, inv.supplier)
            c.setFont("Helvetica", 9); c.drawString(50, y - 44, inv.supplier_addr)
            c.setFont("Helvetica", 10)
            c.drawRightString(w - 50, y, f"Invoice No: {inv.number}")
            if inv.show_date:
                c.drawRightString(w - 50, y - 16, f"Date: {date_text(inv)}")
            if inv.customer:
                c.setFont("Helvetica-Bold", 10); c.drawString(50, y - 80, "Bill To:")
                c.setFont("Helvetica", 10); c.drawString(50, y - 94, inv.customer)
            heads, xs = ["Description", "Qty", "Unit Price", "Amount"], [50, 330, 400, w - 50]
        elif inv.layout == "B":
            c.setFont("Helvetica-Bold", 16); c.drawString(50, y, inv.supplier)
            c.setFont("Helvetica", 9); c.drawString(50, y - 14, inv.supplier_addr)
            c.setFont("Helvetica-Bold", 13); c.drawRightString(w - 50, y, "TAX INVOICE")
            c.setFont("Helvetica", 10)
            c.drawRightString(w - 50, y - 18, f"Invoice # {inv.number}")
            if inv.show_date:
                c.drawRightString(w - 50, y - 32, f"Issue date: {date_text(inv)}")
            if inv.customer:
                c.drawString(50, y - 60, f"Billed to: {inv.customer}")
            heads, xs = ["Item", "Quantity", "Rate", "Line total"], [50, 320, 400, w - 50]
        else:
            c.setFont("Helvetica-Bold", 14); c.drawCentredString(w / 2, y, inv.supplier.upper())
            c.setFont("Helvetica", 9); c.drawCentredString(w / 2, y - 14, inv.supplier_addr)
            c.setFont("Helvetica", 10)
            c.drawString(50, y - 44, f"Bill Number: {inv.number}")
            if inv.show_date:
                c.drawString(50, y - 58, f"Dated: {date_text(inv)}")
            if inv.customer:
                c.drawString(300, y - 44, f"Customer: {inv.customer}")
            heads, xs = ["Particulars", "Qty", "Price", "Amount"], [50, 330, 400, w - 50]
        ty = y - 130
        c.setFont("Helvetica-Bold", 10)
        for j, t in enumerate(heads):
            (c.drawRightString if j else c.drawString)(xs[j], ty, t)
        c.line(50, ty - 5, w - 50, ty - 5)
        c.setFont("Helvetica", 10)
        ty -= 20
        for desc, q, u, a in chunk:
            c.drawString(xs[0], ty, desc)
            c.drawRightString(xs[1], ty, f"{q:g}")
            c.drawRightString(xs[2], ty, money(u))
            c.drawRightString(xs[3], ty, money(a))
            ty -= 17
        if pages > 1:
            c.setFont("Helvetica-Oblique", 8)
            c.drawRightString(w - 50, 30, f"Page {pi + 1} of {pages}" + ("  (continued)" if pi < pages - 1 else ""))
        if pi == pages - 1:
            ty -= 10
            c.line(330, ty + 8, w - 50, ty + 8)
            lab = {"A": ("Subtotal", f"Tax ({inv.tax_rate:g}%)", "Total Due"),
                   "B": ("Sub-total", f"GST {inv.tax_rate:g}%", "Grand Total"),
                   "C": ("Net", f"VAT {inv.tax_rate:g}%", f"Amount Payable ({inv.currency})")}[inv.layout]
            cl = cur_label(inv)
            rows = [(lab[0], money(inv.subtotal))]
            if inv.show_tax:
                rows.append((lab[1], money(inv.tax)))
            rows.append((lab[2], (f"{cl} " if inv.layout != "C" else "") + money(inv.total)))
            for k, (l, v) in enumerate(rows):
                c.setFont("Helvetica-Bold" if k == len(rows) - 1 else "Helvetica", 10)
                c.drawString(330, ty - 6, l); c.drawRightString(w - 50, ty - 6, v)
                ty -= 17
            c.setFont("Helvetica", 8)
            c.drawString(50, 50, "Thank you for your business. Payment due within 30 days.")
        c.showPage()


def pdf_bytes(invs: list[Inv], size=None, password=None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size or R.choice([A4, LETTER]), encrypt=password)
    for inv in invs:
        draw_invoice(c, inv)
    c.save()
    return buf.getvalue()


def render(pdf: bytes, dpi: int) -> list[Image.Image]:
    doc = pdfium.PdfDocument(pdf)
    out = [doc[i].render(scale=dpi / 72).to_pil().convert("L") for i in range(len(doc))]
    doc.close()
    return out


def degrade(img: Image.Image, level: str) -> Image.Image:
    a = np.array(img).astype(np.float32)
    h, w = a.shape
    if level in ("scan", "photo", "poor"):
        angle = R.uniform(-2.5, 2.5) if level != "poor" else R.uniform(-4, 4)
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        a = cv2.warpAffine(a, m, (w, h), borderValue=255)
    if level == "photo":
        d = 0.04 * w
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32([[R.uniform(0, d), R.uniform(0, d)], [w - R.uniform(0, d), R.uniform(0, d)],
                          [w - R.uniform(0, d), h - R.uniform(0, d)], [R.uniform(0, d), h - R.uniform(0, d)]])
        a = cv2.warpPerspective(a, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=200)
        grad = np.tile(np.linspace(0.75, 1.0, w, dtype=np.float32), (h, 1))
        a = a * grad
    noise = {"scan": 9, "photo": 14, "poor": 30}.get(level, 0)
    if noise:
        a = a + np.random.default_rng(R.randint(0, 9999)).normal(0, noise, a.shape)
    if level in ("photo", "poor"):
        k = 3 if level == "photo" else 5
        a = cv2.GaussianBlur(a, (k, k), 0)
    if level == "poor":
        a = 110 + (a - 128) * 0.45
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def jpeg_cycle(img: Image.Image, q: int) -> Image.Image:
    b = io.BytesIO(); img.save(b, "JPEG", quality=q); b.seek(0)
    return Image.open(b).convert("L")


def scanned_pdf(pdf: bytes, level="scan", dpi=200) -> bytes:
    pages = [jpeg_cycle(degrade(p, level), 70) for p in render(pdf, dpi)]
    b = io.BytesIO()
    pages[0].save(b, "PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    return b.getvalue()


# ---------------------------------------------------------------- dataset
class Writer:
    def __init__(self, out: Path):
        self.out = out
        self.labels = {}
        out.mkdir(parents=True, exist_ok=True)

    def add(self, name: str, data: bytes, kind: str, invoices: list[dict], expect="processed", error=None,
            doc_issues=None):
        (self.out / name).write_bytes(data)
        self.labels[name] = {"kind": kind, "expect_status": expect, "expect_error": error,
                             "expect_document_issues": doc_issues or [], "invoices": invoices}


def build(out: Path, big: bool):
    w = Writer(out)
    n = 1
    pdf_invoices: list[Inv] = []

    def nxt(layout, **kw):
        nonlocal n
        inv = new_invoice(n, layout, **kw)
        n += 1
        return inv

    # 1. clean digital PDFs (30), three layouts
    for i in range(30):
        inv = nxt("ABC"[i % 3])
        pdf_invoices.append(inv)
        w.add(f"digital_{i + 1:02d}_{inv.number}.pdf", pdf_bytes([inv]), "pdf_digital", [inv.truth()])

    # 2. planted problems in digital PDFs
    plants = []
    for k in range(5):                       # printed total is wrong
        inv = nxt("ABC"[k % 3]); inv.total = round(inv.total + R.choice([10, 25.5, 100, 0.9, 49.99]), 2)
        inv.expect_issues.append("TOTAL_MISMATCH"); plants.append(("wrong_total", inv))
    for k in range(4):                       # one line amount is wrong
        inv = nxt("ABC"[k % 3], n_items=4); d, q, u, a = inv.items[1]
        inv.items[1] = (d, q, u, round(a + 20, 2))
        inv.expect_issues += ["LINE_ITEM_MATH", "LINE_ITEMS_MISMATCH"]; plants.append(("bad_line", inv))
    for k in range(3):                       # date not printed
        inv = nxt("ABC"[k % 3]); inv.show_date = False
        inv.expect_issues.append("MISSING_FIELD"); plants.append(("no_date", inv))
    for k in range(3):                       # customer not printed
        inv = nxt("ABC"[k % 3]); inv.customer = None
        inv.expect_issues.append("MISSING_FIELD"); plants.append(("no_customer", inv))
    for k in range(2):                       # no tax line at all
        inv = nxt("AB"[k % 2]); inv.show_tax = False; inv.tax = 0.0; inv.tax_rate = 0
        inv.total = inv.subtotal
        inv.expect_issues.append("MISSING_FIELD"); plants.append(("no_tax", inv))
    for k in range(2):                       # ambiguous numeric date
        inv = nxt("C"); dd = date(2026, 3, 4) if k == 0 else date(2026, 5, 6)
        inv.date = dd; inv.date_text = dd.strftime("%m/%d/%Y"); inv.ambiguous_date = True
        inv.expect_issues.append("AMBIGUOUS_DATE"); plants.append(("ambiguous_date", inv))
    for tag, inv in plants:
        pdf_invoices.append(inv)
        w.add(f"issue_{tag}_{inv.number}.pdf", pdf_bytes([inv]), f"pdf_{tag}", [inv.truth()])

    # 3. scanned PDFs (12), photos (8), poor-quality photos (4), clean PNG (5)
    for i in range(12):
        inv = nxt("ABC"[i % 3]); pdf_invoices.append(inv)
        w.add(f"scanned_{i + 1:02d}_{inv.number}.pdf", scanned_pdf(pdf_bytes([inv])), "pdf_scanned", [inv.truth()])
    for i in range(8):
        inv = nxt("ABC"[i % 3]); pdf_invoices.append(inv)
        img = jpeg_cycle(degrade(render(pdf_bytes([inv]), 170)[0], "photo"), 60)
        b = io.BytesIO(); img.save(b, "JPEG", quality=60)
        w.add(f"photo_{i + 1:02d}_{inv.number}.jpg", b.getvalue(), "image_photo", [inv.truth()])
    for i in range(4):
        inv = nxt("AB"[i % 2]); pdf_invoices.append(inv)
        img = degrade(render(pdf_bytes([inv]), 100)[0], "poor")
        b = io.BytesIO(); img.save(b, "JPEG", quality=40)
        t = inv.truth(); t["expect_issues"] = ["READ_FROM_IMAGE"]   # unreadable scans must go to a person
        w.add(f"poor_{i + 1:02d}_{inv.number}.jpg", b.getvalue(), "image_poor", [t])
    for i in range(5):
        inv = nxt("ABC"[i % 3]); pdf_invoices.append(inv)
        b = io.BytesIO(); render(pdf_bytes([inv]), 150)[0].save(b, "PNG")
        w.add(f"clean_{i + 1:02d}_{inv.number}.png", b.getvalue(), "image_png", [inv.truth()])

    # 4. multi-page TIFF (2 files) and multi-invoice PDF batch (2 files)
    for i in range(2):
        invs = [nxt("A"), nxt("B")]
        pages = [degrade(p, "scan") for inv in invs for p in render(pdf_bytes([inv]), 170)]
        b = io.BytesIO(); pages[0].save(b, "TIFF", save_all=True, append_images=pages[1:], compression="tiff_lzw")
        w.add(f"tiff_multipage_{i + 1}.tiff", b.getvalue(), "image_tiff", [x.truth() for x in invs])
        pdf_invoices += invs
    for i in range(2):
        invs = [nxt("ABC"[j % 3], n_items=(24 if j == 2 else None)) for j in range(6)]
        w.add(f"batch_{i + 1}_six_invoices.pdf", pdf_bytes(invs), "pdf_batch", [x.truth() for x in invs])
        pdf_invoices += invs

    # 5. duplicates and conflicting copies
    dup_src = pdf_invoices[0]
    t = dup_src.truth(); t["expect_issues"] = ["DUPLICATE_INVOICE"]
    w.add(f"dup_scan_of_{dup_src.number}.pdf", scanned_pdf(pdf_bytes([dup_src])), "pdf_duplicate", [t])
    dup2 = pdf_invoices[4]
    t = dup2.truth(); t["expect_issues"] = ["DUPLICATE_INVOICE"]
    w.add(f"dup_resent_{dup2.number}.pdf", pdf_bytes([dup2]), "pdf_duplicate", [t])
    conflict = pdf_invoices[7]
    changed = Inv(**{**asdict(conflict), "items": list(conflict.items), "expect_issues": []})
    changed.total = round(conflict.total + 75, 2); changed.subtotal = round(conflict.subtotal + 75, 2)
    t = changed.truth(); t["expect_issues"] = ["CROSS_CHECK_MISMATCH", "LINE_ITEMS_MISMATCH"]
    w.add(f"conflict_revised_{conflict.number}.pdf", pdf_bytes([changed]), "pdf_conflict", [t])
    for lab in w.labels.values():
        for x in lab["invoices"]:
            if x["invoice_number"] == conflict.number and lab["kind"] != "pdf_conflict":
                x["expect_issues"] = sorted(set(x["expect_issues"]) | {"CROSS_CHECK_MISMATCH"})

    # 6. spreadsheets: ledger (xlsx, 3 sheets) cross-checks 14 PDF invoices (3 with different totals)
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Invoices"
    ws.append(["Invoice No", "Invoice Date", "Supplier", "Customer", "Subtotal", "VAT", "Total", "Currency"])
    li = wb.create_sheet("Line Items"); li.append(["Invoice No", "Description", "Qty", "Unit Price", "Amount"])
    ledger_truth = []
    chosen = [x for x in pdf_invoices[1:30] if x is not pdf_invoices[4] and x is not pdf_invoices[7]][:14]
    for j, inv in enumerate(chosen):
        total = inv.total if j not in (2, 6, 11) else round(inv.total + R.choice([15, 120, 3.5]), 2)
        subtotal = inv.subtotal if total == inv.total else round(total - inv.tax, 2)
        ws.append([inv.number, inv.date, inv.supplier, inv.customer, subtotal, inv.tax, total, inv.currency])
        for d, q, u, a in inv.items:
            li.append([inv.number, d, q, u, a])
        ledger_truth.append({"invoice_number": inv.number, "invoice_date": inv.date.isoformat(),
                             "supplier_name": inv.supplier, "customer_name": inv.customer, "subtotal": subtotal,
                             "tax": inv.tax, "total": total, "currency": inv.currency,
                             "expect_issues": ["CROSS_CHECK_MISMATCH", "LINE_ITEMS_MISMATCH"] if total != inv.total
                             else ["LEDGER_MATCH"]})
        if total != inv.total:
            for lab in w.labels.values():
                for x in lab["invoices"]:
                    if x["invoice_number"] == inv.number:
                        x["expect_issues"] = sorted(set(x["expect_issues"]) | {"CROSS_CHECK_MISMATCH"})
    for j in range(6):                        # ledger-only rows (no PDF), incl. planted problems
        inv = nxt("A", currency="USD")
        total = inv.total if j != 3 else round(inv.total + 40, 2)
        number = inv.number if j != 4 else None
        ws.append([number, inv.date, inv.supplier, inv.customer, inv.subtotal, inv.tax, total, inv.currency])
        issues = ["TOTAL_MISMATCH"] if j == 3 else (["MISSING_FIELD"] if j == 4 else [])
        ledger_truth.append({"invoice_number": number, "invoice_date": inv.date.isoformat(), "supplier_name": inv.supplier,
                             "customer_name": inv.customer, "subtotal": inv.subtotal, "tax": inv.tax, "total": total,
                             "currency": inv.currency, "expect_issues": issues})
    last = ledger_truth[-1]                   # the same row entered twice
    ws.append([last["invoice_number"], date.fromisoformat(last["invoice_date"]), last["supplier_name"],
               last["customer_name"], last["subtotal"], last["tax"], last["total"], last["currency"]])
    ledger_truth.append({**last, "expect_issues": ["DUPLICATE_INVOICE"]})
    sm = wb.create_sheet("Summary"); sm.append(["Quarter", "Invoices", "Value"]); sm.append(["Q1 2026", len(ledger_truth), "see Invoices"])
    b = io.BytesIO(); wb.save(b)
    w.add("ledger_q1_2026.xlsx", b.getvalue(), "xlsx_ledger", ledger_truth)

    # legacy XLS register
    import xlwt
    book = xlwt.Workbook(); sh = book.add_sheet("Vendors 2026")
    hdr = ["Bill No", "Date", "Vendor", "Client", "Net Amount", "Tax Amount", "Grand Total", "Curr"]
    for c_, v in enumerate(hdr):
        sh.write(0, c_, v)
    xls_truth = []
    for r_ in range(1, 9):
        inv = nxt("C", currency="BDT")
        vals = [inv.number, inv.date.strftime("%d/%m/%Y") if inv.date.day > 12 else inv.date.isoformat(),
                inv.supplier, inv.customer, inv.subtotal, inv.tax, inv.total, "BDT"]
        for c_, v in enumerate(vals):
            sh.write(r_, c_, v)
        xls_truth.append({"invoice_number": inv.number, "invoice_date": inv.date.isoformat(), "supplier_name": inv.supplier,
                          "customer_name": inv.customer, "subtotal": inv.subtotal, "tax": inv.tax, "total": inv.total,
                          "currency": "BDT", "expect_issues": []})
    b = io.BytesIO(); book.save(b)
    w.add("vendors_legacy_2026.xls", b.getvalue(), "xls_register", xls_truth)

    # CSV exports: US style and EU style (semicolon, decimal comma, dd.mm.yyyy)
    for style in ("us", "eu"):
        rows, truth = [], []
        for _ in range(7):
            inv = nxt("A", currency="USD" if style == "us" else "EUR")
            if style == "us":
                rows.append(f'{inv.number},{inv.date.isoformat()},"{inv.supplier}","{inv.customer}",'
                            f'{inv.subtotal:.2f},{inv.tax:.2f},{inv.total:.2f},USD')
            else:
                rows.append(f'{inv.number};{inv.date.strftime("%d.%m.%Y") if inv.date.day > 12 else inv.date.isoformat()};'
                            f'{inv.supplier};{inv.customer};{money(inv.subtotal, True)};{money(inv.tax, True)};'
                            f'{money(inv.total, True)};EUR')
            truth.append({"invoice_number": inv.number, "invoice_date": inv.date.isoformat(), "supplier_name": inv.supplier,
                          "customer_name": inv.customer, "subtotal": inv.subtotal, "tax": inv.tax, "total": inv.total,
                          "currency": inv.currency, "expect_issues": []})
        head = ("Invoice Number,Date,Supplier,Customer,Subtotal,Tax,Total,Currency" if style == "us"
                else "Invoice Number;Date;Supplier;Customer;Net;VAT;Total;Currency")
        w.add(f"export_{style}.csv", ("\n".join([head] + rows) + "\n").encode("utf-8"), f"csv_{style}", truth)

    # an invoice laid out in a spreadsheet like a printed form (read by the AI)
    inv = nxt("A", currency="USD", n_items=3)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Invoice"
    ws["A1"] = "INVOICE"; ws["A3"] = "From:"; ws["B3"] = inv.supplier; ws["A4"] = "Bill To:"; ws["B4"] = inv.customer
    ws["D3"] = "Invoice No:"; ws["E3"] = inv.number; ws["D4"] = "Date:"; ws["E4"] = date_text(inv)
    ws.append([]); ws.append(["Description", "Qty", "Unit Price", "Amount"])
    for d, q, u, a in inv.items:
        ws.append([d, q, u, a])
    ws.append([]); ws.append(["", "", "Subtotal", inv.subtotal]); ws.append(["", "", f"Tax {inv.tax_rate:g}%", inv.tax])
    ws.append(["", "", "Total (USD)", inv.total])
    b = io.BytesIO(); wb.save(b)
    w.add("invoice_form_layout.xlsx", b.getvalue(), "xlsx_layout", [inv.truth()])

    # 7. broken and unsupported inputs (must fail politely, never crash)
    good = pdf_bytes([nxt("A")])
    w.add("broken_truncated.pdf", good[: len(good) // 3], "corrupted", [], expect="failed_or_flagged",
          error="CORRUPTED_FILE")
    w.add("broken_random_bytes.pdf", bytes(R.getrandbits(8) for _ in range(5000)), "corrupted", [], expect="failed",
          error="CORRUPTED_FILE")
    w.add("broken_empty.png", b"", "corrupted", [], expect="failed", error="EMPTY_FILE")
    xb = io.BytesIO(); openpyxl.Workbook().save(xb)
    w.add("broken_cut.xlsx", xb.getvalue()[:600], "corrupted", [], expect="failed", error="CORRUPTED_FILE")
    w.add("locked_password.pdf", pdf_bytes([nxt("B")], password="secret"), "locked", [], expect="failed",
          error="PASSWORD_PROTECTED")
    w.add("not_really_an_image.jpg", b"this is a text file pretending to be a photo\n" * 20, "corrupted", [],
          expect="failed", error="CORRUPTED_FILE")

    (out / "labels.json").write_text(json.dumps({"seed": 42, "files": w.labels}, indent=1, default=str))
    print(f"{len(w.labels)} files written to {out}")

    if big:
        build_big(out / "big")


def build_big(out: Path, target_pages=1000):
    """One digital PDF of ~1,000 pages holding several hundred invoices (1-3 pages each)."""
    out.mkdir(parents=True, exist_ok=True)
    invs, pages, i = [], 0, 9000
    while pages < target_pages:
        long = R.random() < 0.18
        inv = new_invoice(i, "ABC"[i % 3], n_items=R.choice([19, 25, 40]) if long else None)
        need = max(1, -(-len(inv.items) // 18))
        if pages + need > target_pages:
            inv = new_invoice(i, "A", n_items=2); need = 1
        invs.append(inv); pages += need; i += 1
    (out / "big_batch_1000_pages.pdf").write_bytes(pdf_bytes(invs, size=LETTER))
    (out / "big_labels.json").write_text(json.dumps({"pages": pages, "invoices": [x.truth() for x in invs]}, default=str))
    print(f"big batch: {pages} pages, {len(invs)} invoices")


def build_samples(out: Path):
    """Twelve demo files with their own invoice numbers (seed 7), for the "Try the samples" button."""
    global R
    R = random.Random(7)
    out.mkdir(parents=True, exist_ok=True)
    n = [5001]

    def nxt(layout, **kw):
        inv = new_invoice(n[0], layout, **kw)
        n[0] += 1
        return inv

    a, b, c = nxt("A"), nxt("B"), nxt("C")
    (out / "digital-invoice.pdf").write_bytes(pdf_bytes([a]))
    (out / "scanned-invoice.pdf").write_bytes(scanned_pdf(pdf_bytes([b])))
    img = jpeg_cycle(degrade(render(pdf_bytes([c]), 170)[0], "photo"), 60)
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=60); (out / "phone-photo.jpg").write_bytes(buf.getvalue())
    p = nxt("A")
    img = degrade(render(pdf_bytes([p]), 100)[0], "poor")
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=40); (out / "blurry-photo.jpg").write_bytes(buf.getvalue())
    t1, t2 = nxt("A"), nxt("B")
    pages = [degrade(pg, "scan") for inv in (t1, t2) for pg in render(pdf_bytes([inv]), 170)]
    buf = io.BytesIO(); pages[0].save(buf, "TIFF", save_all=True, append_images=pages[1:], compression="tiff_lzw")
    (out / "two-invoices.tiff").write_bytes(buf.getvalue())
    batch = [nxt("ABC"[j % 3], n_items=(24 if j == 2 else None)) for j in range(6)]
    (out / "batch-six-invoices.pdf").write_bytes(pdf_bytes(batch))
    w = nxt("B"); w.total = round(w.total + 50, 2)
    (out / "wrong-total.pdf").write_bytes(pdf_bytes([w]))
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Invoices"
    ws.append(["Invoice No", "Invoice Date", "Supplier", "Customer", "Subtotal", "VAT", "Total", "Currency"])
    li = wb.create_sheet("Line Items"); li.append(["Invoice No", "Description", "Qty", "Unit Price", "Amount"])
    for k, inv in enumerate([a, b, c] + batch[:3]):
        total = inv.total if k != 4 else round(inv.total + 120, 2)
        ws.append([inv.number, inv.date, inv.supplier, inv.customer, round(total - inv.tax, 2), inv.tax, total, inv.currency])
        for d, q, u, amt in inv.items:
            li.append([inv.number, d, q, u, amt])
    extra = nxt("A", currency="USD")
    for _ in range(2):  # the same row typed twice
        ws.append([extra.number, extra.date, extra.supplier, extra.customer, extra.subtotal, extra.tax, extra.total, "USD"])
    sm = wb.create_sheet("Summary"); sm.append(["Quarter", "Invoices", "Value"]); sm.append(["Q1 2026", 8, "see Invoices"])
    buf = io.BytesIO(); wb.save(buf); (out / "ledger-q1-2026.xlsx").write_bytes(buf.getvalue())
    import xlwt
    book = xlwt.Workbook(); sh = book.add_sheet("Vendors 2026")
    for col, v in enumerate(["Bill No", "Date", "Vendor", "Client", "Net Amount", "Tax Amount", "Grand Total", "Curr"]):
        sh.write(0, col, v)
    for r_ in range(1, 6):
        inv = nxt("C", currency="BDT")
        for col, v in enumerate([inv.number, inv.date.isoformat(), inv.supplier, inv.customer, inv.subtotal, inv.tax, inv.total, "BDT"]):
            sh.write(r_, col, v)
    buf = io.BytesIO(); book.save(buf); (out / "vendors-legacy.xls").write_bytes(buf.getvalue())
    rows = ["Invoice Number;Date;Supplier;Customer;Net;VAT;Total;Currency"]
    for _ in range(5):
        inv = nxt("A", currency="EUR")
        rows.append(f"{inv.number};{inv.date.isoformat()};{inv.supplier};{inv.customer};{money(inv.subtotal, True)};"
                    f"{money(inv.tax, True)};{money(inv.total, True)};EUR")
    (out / "export-eu.csv").write_text("\n".join(rows) + "\n")
    good = pdf_bytes([nxt("A")])
    (out / "damaged.pdf").write_bytes(good[: len(good) // 3])
    (out / "locked.pdf").write_bytes(pdf_bytes([nxt("B")], password="secret"))
    print("samples:", sorted(x.name for x in out.iterdir()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dataset/out")
    ap.add_argument("--big", action="store_true")
    ap.add_argument("--samples", action="store_true", help="write the 12 demo sample files instead")
    a = ap.parse_args()
    if a.samples:
        build_samples(Path(a.out))
    else:
        build(Path(a.out), a.big)
