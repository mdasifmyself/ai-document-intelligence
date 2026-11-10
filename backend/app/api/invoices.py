"""Inspect, correct and approve extracted invoices. Every manual change is stored with who, when, why."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..ai import client
from ..ai.client import AIUnavailable
from ..db import get_db
from ..models import Correction, CrossCheck, Document, Invoice, ValidationIssue
from ..pipeline.matching import refresh_document, refresh_invoice, run_matching
from ..pipeline.normalize import normalize_currency, normalize_invoice_number, normalize_name, parse_amount, parse_date
from ..pipeline.runner import _save_issues, _search_text
from ..pipeline.types import CORE_FIELDS, ExtractedInvoice, FieldValue
from ..pipeline.validate import validate
from ..schemas import CorrectionIn, InvoiceDetail, InvoiceOut, Page
from ..security import require_access

router = APIRouter(prefix="/invoices", tags=["Invoices"], dependencies=[Depends(require_access)])
EDITABLE = set(CORE_FIELDS) | {"line_items"}


def _detail(db: Session, inv: Invoice) -> InvoiceDetail:
    db.refresh(inv)
    doc = db.get(Document, inv.document_id)
    out = InvoiceDetail.model_validate(inv, from_attributes=True)
    return out.model_copy(update={"document_filename": doc.filename, "document_file_type": doc.file_type})


def _get(db: Session, inv_id: uuid.UUID) -> Invoice:
    inv = db.scalar(select(Invoice).where(Invoice.id == inv_id)
                    .options(selectinload(Invoice.issues), selectinload(Invoice.corrections)))
    if not inv:
        raise HTTPException(404, "Invoice not found.")
    return inv


def to_extracted(inv: Invoice, doc: Document) -> ExtractedInvoice:
    fields = {}
    for name in CORE_FIELDS:
        meta = (inv.fields or {}).get(name)
        if meta is None and inv.source_kind == "record" and getattr(inv, name) is None:
            continue
        meta = meta or {}
        value = getattr(inv, name)
        fields[name] = FieldValue(value=Decimal(str(value)) if name in ("subtotal", "tax", "total") and value is not None
                                  else value, evidence=meta.get("evidence"), raw=meta.get("raw"),
                                  verified=meta.get("verified"), confidence=meta.get("confidence") or 0,
                                  source=meta.get("source") or "text")
    return ExtractedInvoice(fields=fields, line_items=inv.line_items or [], method=inv.extraction_method or "",
                            source_kind=inv.source_kind, location=inv.location or {},
                            ocr_confidence=doc.ocr_confidence if doc.text_method in ("ocr", "mixed") else None)


def revalidate(db: Session, inv: Invoice):
    """Re-run validation and cross-checks after a change."""
    doc = db.get(Document, inv.document_id)
    db.execute(delete(ValidationIssue).where(ValidationIssue.invoice_id == inv.id))
    db.execute(delete(ValidationIssue).where(ValidationIssue.details["other_invoice_id"].astext == str(inv.id)))
    others = db.scalars(select(CrossCheck).where(or_(CrossCheck.invoice_a == inv.id, CrossCheck.invoice_b == inv.id))).all()
    other_ids = {c.invoice_b if c.invoice_a == inv.id else c.invoice_a for c in others}
    for c in others:
        db.delete(c)
    db.flush()
    _save_issues(db, inv.document_id, inv, validate(to_extracted(inv, doc)))
    db.flush()
    db.refresh(doc)
    run_matching(db, doc)
    refresh_invoice(db, inv)
    for oid in other_ids:
        o = db.get(Invoice, oid)
        if o:
            refresh_invoice(db, o)
            refresh_document(db, db.get(Document, o.document_id))
    refresh_document(db, doc)


def _clean(field: str, value):
    if value is None or value == "":
        return None
    if field in ("subtotal", "tax", "total"):
        d = parse_amount(value)
        if d is None:
            raise HTTPException(422, f"{field}: '{value}' is not a number.")
        return d
    if field == "invoice_date":
        d, _ = parse_date(value)
        if d is None:
            raise HTTPException(422, f"invoice_date: '{value}' is not a date (use YYYY-MM-DD).")
        return d
    if field == "currency":
        c = normalize_currency(value)
        if c is None:
            raise HTTPException(422, f"currency: '{value}' is not a known ISO 4217 code.")
        return c
    if field == "line_items":
        if not isinstance(value, list):
            raise HTTPException(422, "line_items must be a list.")
        items = []
        for it in value:
            items.append({"description": str(it.get("description", ""))[:500],
                          "quantity": float(q) if (q := parse_amount(it.get("quantity"))) is not None else None,
                          "unit_price": float(p) if (p := parse_amount(it.get("unit_price"))) is not None else None,
                          "amount": float(a) if (a := parse_amount(it.get("amount"))) is not None else None,
                          "evidence": "manual", "verified": True})
        return items
    return str(value).strip()[:255]


def _jsonable(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


@router.get("", response_model=Page, summary="List and filter invoices")
def list_invoices(needs_review: bool | None = None, status: str | None = None, supplier: str | None = None,
                  currency: str | None = None, document_id: uuid.UUID | None = None, issue_code: str | None = None,
                  date_from: str | None = None, date_to: str | None = None,
                  min_total: float | None = None, max_total: float | None = None,
                  page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), db: Session = Depends(get_db)):
    stmt = select(Invoice)
    if needs_review is not None:
        stmt = stmt.where(Invoice.needs_review == needs_review)
    if status:
        stmt = stmt.where(Invoice.status.in_(status.split(",")))
    if supplier:
        stmt = stmt.where(Invoice.supplier_name.ilike(f"%{supplier}%"))
    if currency:
        stmt = stmt.where(Invoice.currency == currency.upper())
    if document_id:
        stmt = stmt.where(Invoice.document_id == document_id)
    if issue_code:
        stmt = stmt.where(Invoice.id.in_(select(ValidationIssue.invoice_id).where(ValidationIssue.code.in_(issue_code.split(",")))))
    if date_from:
        stmt = stmt.where(Invoice.invoice_date >= parse_date(date_from)[0])
    if date_to:
        stmt = stmt.where(Invoice.invoice_date <= parse_date(date_to)[0])
    if min_total is not None:
        stmt = stmt.where(Invoice.total >= min_total)
    if max_total is not None:
        stmt = stmt.where(Invoice.total <= max_total)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Invoice.needs_review.desc(), Invoice.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    names = dict(db.execute(select(Document.id, Document.filename).where(Document.id.in_({r.document_id for r in rows}))).all())
    codes: dict = {}
    for iid, code in db.execute(select(ValidationIssue.invoice_id, ValidationIssue.code).where(
            ValidationIssue.invoice_id.in_([r.id for r in rows]), ValidationIssue.severity != "info")).all():
        codes.setdefault(iid, []).append(code)
    items = [InvoiceOut.model_validate(r, from_attributes=True).model_dump()
             | {"document_filename": names.get(r.document_id), "issue_codes": sorted(set(codes.get(r.id, [])))}
             for r in rows]
    return Page(items=items, total=total or 0, page=page, page_size=page_size)


@router.get("/{inv_id}", response_model=InvoiceDetail, summary="One invoice with issues and correction history")
def get_invoice(inv_id: uuid.UUID, db: Session = Depends(get_db)):
    return _detail(db, _get(db, inv_id))


@router.patch("/{inv_id}", response_model=InvoiceDetail, summary="Correct values by hand")
def correct(inv_id: uuid.UUID, body: CorrectionIn, db: Session = Depends(get_db)):
    """Each changed field is saved as a correction (old value, new value, who, why). Validation and
    cross-checks run again immediately, so the flags update."""
    inv = _get(db, inv_id)
    unknown = set(body.fields) - EDITABLE
    if unknown:
        raise HTTPException(422, f"These fields cannot be edited: {', '.join(sorted(unknown))}.")
    changed = False
    meta = dict(inv.fields or {})
    for field, raw in body.fields.items():
        new = _clean(field, raw)
        old = inv.line_items if field == "line_items" else getattr(inv, field)
        if _jsonable(old) == _jsonable(new):
            continue
        db.add(Correction(invoice_id=inv.id, field=field, old_value=_jsonable(old), new_value=_jsonable(new),
                          reason=body.reason, corrected_by=body.corrected_by))
        setattr(inv, field, new)
        if field != "line_items":
            meta[field] = {"value": _jsonable(new), "evidence": f"Corrected by {body.corrected_by}", "raw": None,
                           "verified": True, "confidence": 1.0, "source": "manual"}
        changed = True
    if not changed:
        return _detail(db, inv)
    inv.fields = meta
    inv.invoice_number_norm = normalize_invoice_number(inv.invoice_number)
    inv.supplier_norm = normalize_name(inv.supplier_name)
    inv.search_text = _search_text(inv)
    if inv.status == "reviewed":
        inv.status = "needs_review"
    db.flush()
    revalidate(db, inv)
    try:
        inv.embedding = client.embed([inv.search_text])[0]
    except AIUnavailable:
        pass
    db.commit()
    return _detail(db, inv)


@router.post("/{inv_id}/approve", response_model=InvoiceDetail, summary="Mark as reviewed by a person")
def approve(inv_id: uuid.UUID, reviewer: str = Query("reviewer", max_length=120), db: Session = Depends(get_db)):
    inv = _get(db, inv_id)
    db.add(Correction(invoice_id=inv.id, field="status", old_value=inv.status, new_value="reviewed",
                      reason="Approved after review", corrected_by=reviewer))
    inv.status, inv.needs_review, inv.reviewed_at = "reviewed", False, datetime.now(timezone.utc)
    db.flush()
    refresh_document(db, db.get(Document, inv.document_id))
    db.commit()
    return _detail(db, inv)
