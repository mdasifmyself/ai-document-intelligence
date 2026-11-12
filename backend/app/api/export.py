"""Excel export: everything (or a filtered part) as a formatted .xlsx workbook.

Sheets: Summary · Invoices · Line items · Issues · Cross-checks · Documents
Each sheet has a styled header row, frozen panes, filters, number and date formats.
"""
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CrossCheck, Document, Invoice, ValidationIssue
from ..pipeline.normalize import parse_date
from ..security import require_access

router = APIRouter(tags=["Export"], dependencies=[Depends(require_access)])

HEAD_FILL = PatternFill("solid", fgColor="1C3461")   # Cottage Home Care navy
HEAD_FONT = Font(bold=True, color="FFFFFF")
REVIEW_FILL = PatternFill("solid", fgColor="FDF6E7")
ERROR_FILL = PatternFill("solid", fgColor="FDEEEE")
MONEY = "#,##0.00"


def _sheet(wb: Workbook, title: str, headers: list[str], rows: list[list], widths: list[int], money_cols=(), date_cols=()):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 22
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for col in money_cols:
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell:
                c.number_format = MONEY
    for col in date_cols:
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell:
                c.number_format = "yyyy-mm-dd"
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    return ws


@router.get("/export.xlsx", summary="Download results as an Excel workbook",
            responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
def export_xlsx(needs_review: bool | None = None, status: str | None = Query(None, description="Document status filter"),
                document_id: uuid.UUID | None = None, supplier: str | None = None, currency: str | None = None,
                date_from: str | None = None, date_to: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Invoice, Document).join(Document, Document.id == Invoice.document_id)
    if needs_review is not None:
        stmt = stmt.where(Invoice.needs_review == needs_review)
    if status:
        stmt = stmt.where(Document.status.in_(status.split(",")))
    if document_id:
        stmt = stmt.where(Invoice.document_id == document_id)
    if supplier:
        stmt = stmt.where(Invoice.supplier_name.ilike(f"%{supplier}%"))
    if currency:
        stmt = stmt.where(Invoice.currency == currency.upper())
    if date_from and (d := parse_date(date_from)[0]):
        stmt = stmt.where(Invoice.invoice_date >= d)
    if date_to and (d := parse_date(date_to)[0]):
        stmt = stmt.where(Invoice.invoice_date <= d)
    pairs = db.execute(stmt.order_by(Document.created_at, Invoice.seq)).all()
    inv_ids = [i.id for i, _ in pairs]
    doc_ids = sorted({d.id for _, d in pairs}, key=str) if (document_id or needs_review is not None or status or supplier
                                                             or currency or date_from or date_to) else None

    issues = db.scalars(select(ValidationIssue).where(ValidationIssue.invoice_id.in_(inv_ids))).all() if inv_ids else []
    issues_by_inv: dict = {}
    for i in issues:
        issues_by_inv.setdefault(i.invoice_id, []).append(i)

    wb = Workbook()
    wb.remove(wb.active)
    now = datetime.now(timezone.utc)

    inv_rows = []
    for inv, doc in pairs:
        its = issues_by_inv.get(inv.id, [])
        loc = inv.location or {}
        where = (f"pages {', '.join(map(str, loc['pages']))}" if loc.get("pages")
                 else f"{loc.get('sheet', '')} row {loc.get('row', '')}".strip())
        inv_rows.append([
            inv.invoice_number, inv.invoice_date, inv.supplier_name, inv.customer_name,
            float(inv.subtotal) if inv.subtotal is not None else None, float(inv.tax) if inv.tax is not None else None,
            float(inv.total) if inv.total is not None else None, inv.currency, len(inv.line_items or []),
            {"ok": "Checked", "needs_review": "Needs review", "reviewed": "Approved"}.get(inv.status, inv.status),
            "; ".join(sorted({i.code for i in its if i.severity != "info"})), round(inv.confidence or 0, 2),
            {"llm_text": "AI from text", "llm_vision": "AI from image", "spreadsheet_columns": "Spreadsheet columns"}
            .get(inv.extraction_method or "", inv.extraction_method), doc.filename, where, str(inv.id)])
    ws = _sheet(wb, "Invoices", ["Invoice number", "Invoice date", "Supplier", "Customer", "Subtotal", "Tax", "Total",
                                 "Currency", "Line items", "Status", "Problems", "Confidence", "Read with", "Source file",
                                 "Location", "Invoice ID"],
                inv_rows, [18, 13, 30, 28, 13, 11, 13, 9, 10, 14, 34, 11, 18, 34, 16, 38], money_cols=(5, 6, 7),
                date_cols=(2,))
    for r, (inv, _) in enumerate(pairs, start=2):
        if inv.needs_review:
            for c in ws[r]:
                c.fill = REVIEW_FILL

    li_rows = []
    for inv, doc in pairs:
        for n, li in enumerate(inv.line_items or [], start=1):
            li_rows.append([inv.invoice_number, n, li.get("description"), li.get("quantity"), li.get("unit_price"),
                            li.get("amount"), inv.currency, doc.filename])
    _sheet(wb, "Line items", ["Invoice number", "Line", "Description", "Quantity", "Unit price", "Amount", "Currency",
                              "Source file"], li_rows, [18, 6, 42, 10, 13, 13, 9, 34], money_cols=(5, 6))

    inv_by_id = {i.id: (i, d) for i, d in pairs}
    is_rows = [[inv_by_id[i.invoice_id][0].invoice_number, i.severity.capitalize(), i.code, i.field, i.message,
                inv_by_id[i.invoice_id][1].filename] for i in sorted(issues, key=lambda x: (x.severity != "error", x.code))
               if i.invoice_id in inv_by_id]
    ws = _sheet(wb, "Issues", ["Invoice number", "Severity", "Code", "Field", "What is wrong", "Source file"], is_rows,
                [18, 10, 24, 16, 80, 34])
    for r, row in enumerate(is_rows, start=2):
        if row[1] == "Error":
            ws.cell(r, 2).fill = ERROR_FILL
        ws.cell(r, 5).alignment = Alignment(wrap_text=True, vertical="top")

    checks = db.scalars(select(CrossCheck).where((CrossCheck.invoice_a.in_(inv_ids)) | (CrossCheck.invoice_b.in_(inv_ids)))).all() \
        if inv_ids else []
    cc_rows = []
    for c in checks:
        a, b = db.get(Invoice, c.invoice_a), db.get(Invoice, c.invoice_b)
        da, dbb = db.get(Document, a.document_id), db.get(Document, b.document_id)
        cc_rows.append([a.invoice_number, c.kind.replace("_", " ↔ ").upper(), {"match": "Match", "mismatch": "Values differ",
                        "duplicate": "Duplicate"}[c.status], da.filename, dbb.filename,
                        "; ".join(f"{d['field']}: {d['a']} vs {d['b']}" for d in c.differences or [])])
    _sheet(wb, "Cross-checks", ["Invoice number", "Compared", "Result", "Document A", "Document B", "Differences"], cc_rows,
           [18, 16, 14, 34, 34, 60])

    docs = db.scalars(select(Document).where(Document.id.in_(doc_ids)) if doc_ids is not None else select(Document)
                      .order_by(Document.created_at)).all()
    d_rows = [[d.filename, (d.file_type or "").upper(), {"queued": "Waiting", "processing": "Processing", "completed": "Done",
               "needs_review": "Needs review", "failed": "Failed"}.get(d.status, d.status), d.page_count, d.text_method,
               d.ocr_confidence, d.invoice_count, d.issue_count, d.error_code, d.error_message,
               round((d.processing_ms or 0) / 1000, 2) if d.processing_ms else None, d.attempts,
               d.created_at.replace(tzinfo=None) if d.created_at else None] for d in docs]
    _sheet(wb, "Documents", ["File", "Type", "Status", "Pages", "Read with", "OCR confidence", "Invoices", "Problems",
                             "Error code", "Error", "Seconds", "Attempts", "Uploaded (UTC)"], d_rows,
           [36, 7, 13, 7, 12, 14, 9, 9, 20, 50, 9, 9, 19])

    s = wb.create_sheet("Summary", 0)
    s["A1"] = "DocIntel export"
    s["A1"].font = Font(bold=True, size=14)
    rows = [("Exported (UTC)", now.strftime("%Y-%m-%d %H:%M")), ("Invoices", len(inv_rows)),
            ("Needing review", sum(1 for i, _ in pairs if i.needs_review)), ("Line items", len(li_rows)),
            ("Problems listed", len(is_rows)), ("Cross-checks", len(cc_rows)), ("Documents", len(d_rows))]
    filters = {k: v for k, v in {"needs_review": needs_review, "status": status, "supplier": supplier, "currency": currency,
                                 "date_from": date_from, "date_to": date_to, "document_id": document_id}.items() if v is not None}
    rows.append(("Filters", ", ".join(f"{k}={v}" for k, v in filters.items()) or "none (everything)"))
    for r, (k, v) in enumerate(rows, start=3):
        s.cell(r, 1, k).font = Font(bold=True)
        s.cell(r, 2, v)
    s.column_dimensions["A"].width, s.column_dimensions["B"].width = 20, 50
    s["A12"] = "Rows highlighted in the Invoices sheet need review. Problems are explained in the Issues sheet."

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = f"docintel-export-{now.strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
