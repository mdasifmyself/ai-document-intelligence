"""Duplicates and cross-document verification (PDF ↔ PDF, PDF ↔ Excel, image ↔ CSV, ...).

Two invoices are "the same invoice" when their invoice numbers match after cleaning and their supplier
names agree (or one side, such as a ledger row, has no supplier column).

  document ↔ document, all key values equal  -> DUPLICATE_INVOICE (submitted twice)
  document ↔ document, values differ         -> CROSS_CHECK_MISMATCH on both (conflicting versions)
  document ↔ spreadsheet row, equal          -> LEDGER_MATCH (info: confirmed by the ledger)
  document ↔ spreadsheet row, values differ  -> CROSS_CHECK_MISMATCH on both
  two rows in the same spreadsheet           -> DUPLICATE_INVOICE
Same supplier + same total + same date under a different number -> POSSIBLE_DUPLICATE (warning).
"""
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..models import CrossCheck, Document, Invoice, ValidationIssue
from .validate import tolerance

GROUP = {"pdf": "pdf", "image": "image", "xlsx": "excel", "xls": "excel", "csv": "csv"}
COMPARE = ("total", "subtotal", "tax", "invoice_date", "currency", "customer_name")


def _same_supplier(a: Invoice, b: Invoice) -> bool:
    if not a.supplier_norm or not b.supplier_norm:
        return True
    return fuzz.token_set_ratio(a.supplier_norm, b.supplier_norm) >= 85


def differences(a: Invoice, b: Invoice) -> list[dict]:
    out = []
    for f in COMPARE:
        va, vb = getattr(a, f), getattr(b, f)
        if va is None or vb is None:
            continue
        if f in ("total", "subtotal", "tax"):
            da, db = Decimal(str(va)), Decimal(str(vb))
            if abs(da - db) > tolerance(max(abs(da), abs(db))):
                out.append({"field": f, "a": float(da), "b": float(db)})
        elif f == "customer_name":
            if fuzz.token_set_ratio(str(va).lower(), str(vb).lower()) < 85:
                out.append({"field": f, "a": va, "b": vb})
        elif va != vb:
            out.append({"field": f, "a": str(va), "b": str(vb)})
    return out


def _where(doc: Document, inv: Invoice) -> str:
    loc = inv.location or {}
    if "sheet" in loc and "row" in loc:
        return f"{doc.filename} (sheet {loc['sheet']}, row {loc['row']})"
    if loc.get("pages"):
        p = loc["pages"]
        return f"{doc.filename} (page {p[0]}{'–' + str(p[-1]) if len(p) > 1 else ''})"
    return doc.filename


def _add_issue(s: Session, inv: Invoice, code: str, severity: str, message: str, details: dict, field=None):
    exists = s.scalar(select(ValidationIssue.id).where(
        ValidationIssue.invoice_id == inv.id, ValidationIssue.code == code,
        ValidationIssue.details["other_invoice_id"].astext == details.get("other_invoice_id", "")))
    if not exists:
        s.add(ValidationIssue(document_id=inv.document_id, invoice_id=inv.id, code=code, severity=severity,
                              field=field, message=message, details=details))


def _fmt_diffs(diffs: list[dict]) -> str:
    return "; ".join(f"{d['field']}: {d['a']} vs {d['b']}" for d in diffs)


def run_matching(s: Session, doc: Document) -> int:
    """Compare every invoice of `doc` with all earlier invoices. Returns the number of checks recorded."""
    count = 0
    for inv in doc.invoices:
        if not inv.invoice_number_norm:
            continue
        candidates = s.scalars(select(Invoice).where(
            Invoice.invoice_number_norm == inv.invoice_number_norm, Invoice.id != inv.id)).all()
        for other in candidates:
            if not _same_supplier(inv, other):
                continue
            pair = sorted([inv.id, other.id], key=str)
            if s.scalar(select(CrossCheck.id).where(CrossCheck.invoice_a == pair[0], CrossCheck.invoice_b == pair[1])):
                continue
            other_doc = s.get(Document, other.document_id)
            kinds = sorted([GROUP.get(doc.file_type or "", "file"), GROUP.get(other_doc.file_type or "", "file")],
                           key=lambda k: ["pdf", "image", "excel", "csv", "file"].index(k))
            kind = f"{kinds[0]}_{kinds[1]}"
            diffs = differences(inv, other)
            both_docs = inv.source_kind == "document" and other.source_kind == "document"
            same_sheet_rows = inv.source_kind == other.source_kind == "record" and inv.document_id == other.document_id
            if diffs:
                status = "mismatch"
                for a, b, bdoc in ((inv, other, other_doc), (other, inv, doc)):
                    _add_issue(s, a, "CROSS_CHECK_MISMATCH", "error",
                               f"The same invoice in {_where(bdoc, b)} has different values: {_fmt_diffs(diffs)}.",
                               {"other_invoice_id": str(b.id), "differences": diffs, "kind": kind})
            elif both_docs or same_sheet_rows:
                status = "duplicate"
                inv_key = (doc.created_at, inv.seq)
                other_key = (other_doc.created_at, other.seq)
                newer, older, older_doc = (inv, other, other_doc) if inv_key >= other_key else (other, inv, doc)
                _add_issue(s, newer, "DUPLICATE_INVOICE", "error",
                           f"This invoice was already received in {_where(older_doc, older)}.",
                           {"other_invoice_id": str(older.id), "kind": kind})
            else:
                status = "match"
                for a, b, bdoc in ((inv, other, other_doc), (other, inv, doc)):
                    _add_issue(s, a, "LEDGER_MATCH", "info", f"Confirmed by {_where(bdoc, b)}: all values agree.",
                               {"other_invoice_id": str(b.id), "kind": kind})
            s.add(CrossCheck(invoice_a=pair[0], invoice_b=pair[1], kind=kind, status=status, differences=diffs))
            count += 1
            if other.document_id != doc.id:
                s.flush()
                refresh_invoice(s, other)
                refresh_document(s, other_doc)

    # near-duplicates: same supplier, total and date, different number
    for inv in doc.invoices:
        if inv.source_kind != "document" or not (inv.supplier_norm and inv.total is not None and inv.invoice_date):
            continue
        near = s.scalars(select(Invoice).where(
            Invoice.id != inv.id, Invoice.source_kind == "document", Invoice.supplier_norm == inv.supplier_norm,
            Invoice.total == inv.total, Invoice.invoice_date == inv.invoice_date,
            or_(Invoice.invoice_number_norm.is_(None),
                and_(Invoice.invoice_number_norm.is_not(None), Invoice.invoice_number_norm != (inv.invoice_number_norm or ""))))
        ).all()
        for other in near:
            other_doc = s.get(Document, other.document_id)
            _add_issue(s, inv, "POSSIBLE_DUPLICATE", "warning",
                       f"Same supplier, date and total as {_where(other_doc, other)} but a different invoice number.",
                       {"other_invoice_id": str(other.id)})
    s.flush()
    return count


def refresh_invoice(s: Session, inv: Invoice):
    issues = s.scalars(select(ValidationIssue).where(ValidationIssue.invoice_id == inv.id)).all()
    review = any(i.severity in ("error", "warning") for i in issues)
    inv.needs_review = review and inv.status != "reviewed"
    if inv.status != "reviewed":
        inv.status = "needs_review" if review else "ok"


def refresh_document(s: Session, doc: Document):
    if doc.status in ("queued", "processing", "failed"):
        return
    s.flush()
    invs = s.scalars(select(Invoice).where(Invoice.document_id == doc.id)).all()
    doc_level = s.scalars(select(ValidationIssue).where(ValidationIssue.document_id == doc.id,
                                                        ValidationIssue.invoice_id.is_(None))).all()
    all_issues = s.scalars(select(ValidationIssue).where(ValidationIssue.document_id == doc.id)).all()
    doc.invoice_count = len(invs)
    doc.issue_count = sum(1 for i in all_issues if i.severity in ("error", "warning"))
    review = any(i.needs_review for i in invs) or any(i.severity in ("error", "warning") for i in doc_level)
    doc.status = "needs_review" if review else "completed"
