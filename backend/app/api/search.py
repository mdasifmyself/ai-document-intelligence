"""Search: keyword (PostgreSQL full-text + fuzzy name match), semantic (pgvector), or hybrid (both, fused)."""
import time
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..ai import client
from ..ai.client import AIUnavailable
from ..db import get_db
from ..models import CrossCheck, Document, Invoice
from ..pipeline.normalize import parse_date
from ..schemas import CrossCheckOut, InvoiceOut, SearchHit, SearchOut
from ..security import require_access

router = APIRouter(tags=["Search"], dependencies=[Depends(require_access)])
RRF_K = 60
MIN_SEMANTIC = 0.2


def _filtered(stmt, supplier, currency, date_from, date_to, min_total, max_total, needs_review, file_type):
    if supplier:
        stmt = stmt.where(Invoice.supplier_name.ilike(f"%{supplier}%"))
    if currency:
        stmt = stmt.where(Invoice.currency == currency.upper())
    if date_from and (d := parse_date(date_from)[0]):
        stmt = stmt.where(Invoice.invoice_date >= d)
    if date_to and (d := parse_date(date_to)[0]):
        stmt = stmt.where(Invoice.invoice_date <= d)
    if min_total is not None:
        stmt = stmt.where(Invoice.total >= min_total)
    if max_total is not None:
        stmt = stmt.where(Invoice.total <= max_total)
    if needs_review is not None:
        stmt = stmt.where(Invoice.needs_review == needs_review)
    if file_type:
        stmt = stmt.where(Document.file_type.in_(file_type.split(",")))
    return stmt


@router.get("/search", response_model=SearchOut, summary="Search processed invoices")
def search(q: str = Query("", max_length=300, description="Words or a question, e.g. 'cleaning services in March'"),
           mode: str = Query("hybrid", pattern="^(hybrid|keyword|semantic)$"),
           supplier: str | None = None, currency: str | None = None, date_from: str | None = None,
           date_to: str | None = None, min_total: float | None = None, max_total: float | None = None,
           needs_review: bool | None = None, file_type: str | None = None,
           limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    t0 = time.monotonic()
    base = select(Invoice, Document.filename, Document.file_type).join(Document, Document.id == Invoice.document_id)
    base = _filtered(base, supplier, currency, date_from, date_to, min_total, max_total, needs_review, file_type)
    q = q.strip()
    keyword: list[tuple] = []
    semantic: list[tuple] = []

    if not q:
        rows = db.execute(base.order_by(Invoice.invoice_date.desc().nulls_last()).limit(limit)).all()
        hits = [SearchHit(invoice=InvoiceOut.model_validate(r[0], from_attributes=True), document_filename=r[1],
                          document_file_type=r[2], score=1.0, match="keyword") for r in rows]
        return SearchOut(query=q, mode=mode, total=len(hits), took_ms=int((time.monotonic() - t0) * 1000), hits=hits)

    if mode in ("keyword", "hybrid"):
        tsq = func.websearch_to_tsquery("english", q)
        # word_similarity compares the query with the best-matching words of the name, so a typo such as
        # "Northwnd" still finds "Northwind Medical Supplies Ltd"
        rank = (func.ts_rank_cd(Invoice.search_tsv, tsq) + func.greatest(
            func.word_similarity(q, func.coalesce(Invoice.supplier_name, "")),
            func.word_similarity(q, func.coalesce(Invoice.customer_name, "")),
            func.similarity(func.coalesce(Invoice.invoice_number, ""), q))).label("rank")
        snippet = func.ts_headline("english", func.coalesce(Invoice.search_text, ""), tsq,
                                   "StartSel=<mark>,StopSel=</mark>,MaxWords=18,MinWords=6").label("snippet")
        stmt = base.add_columns(rank, snippet).where(or_(
            Invoice.search_tsv.op("@@")(tsq),
            func.word_similarity(q, func.coalesce(Invoice.supplier_name, "")) > 0.5,
            func.word_similarity(q, func.coalesce(Invoice.customer_name, "")) > 0.5,
            Invoice.invoice_number.ilike(f"%{q}%"),
        )).order_by(rank.desc()).limit(limit * 2)
        keyword = db.execute(stmt).all()

    if mode in ("semantic", "hybrid"):
        try:
            vec = client.embed([q])[0]
            dist = Invoice.embedding.cosine_distance(vec).label("dist")
            stmt = base.add_columns(dist).where(Invoice.embedding.is_not(None)).order_by(dist).limit(limit * 2)
            semantic = [r for r in db.execute(stmt).all() if 1 - r[3] >= MIN_SEMANTIC]
        except AIUnavailable:
            semantic = []

    scores: dict[uuid.UUID, dict] = {}
    for rank_i, r in enumerate(keyword):
        e = scores.setdefault(r[0].id, {"row": r, "score": 0.0, "kinds": set(), "snippet": r[4]})
        e["score"] += 1 / (RRF_K + rank_i + 1) if mode == "hybrid" else float(r[3])
        e["kinds"].add("keyword")
    for rank_i, r in enumerate(semantic):
        e = scores.setdefault(r[0].id, {"row": r, "score": 0.0, "kinds": set(), "snippet": None})
        e["score"] += 1 / (RRF_K + rank_i + 1) if mode == "hybrid" else 1 - float(r[3])
        e["kinds"].add("semantic")
    ranked = sorted(scores.values(), key=lambda e: e["score"], reverse=True)[:limit]
    hits = []
    for e in ranked:
        r = e["row"]
        match = "hybrid" if len(e["kinds"]) == 2 else next(iter(e["kinds"]))
        hits.append(SearchHit(invoice=InvoiceOut.model_validate(r[0], from_attributes=True), document_filename=r[1],
                              document_file_type=r[2], score=round(e["score"], 4), match=match, snippet=e["snippet"]))
    return SearchOut(query=q, mode=mode, total=len(hits), took_ms=int((time.monotonic() - t0) * 1000), hits=hits)


@router.get("/cross-checks", response_model=list[CrossCheckOut], summary="Same invoice found in two documents")
def cross_checks(status: str | None = Query(None, description="match, mismatch or duplicate"),
                 kind: str | None = Query(None, description="e.g. pdf_excel, pdf_pdf"),
                 limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    stmt = select(CrossCheck)
    if status:
        stmt = stmt.where(CrossCheck.status.in_(status.split(",")))
    if kind:
        stmt = stmt.where(CrossCheck.kind == kind)
    rows = db.scalars(stmt.order_by(CrossCheck.created_at.desc()).limit(limit)).all()
    out = []
    for c in rows:
        side = {}
        for key, iid in (("a", c.invoice_a), ("b", c.invoice_b)):
            inv = db.get(Invoice, iid)
            doc = db.get(Document, inv.document_id) if inv else None
            side[key] = {"invoice_id": str(iid), "invoice_number": inv.invoice_number if inv else None,
                         "supplier_name": inv.supplier_name if inv else None,
                         "total": float(inv.total) if inv and inv.total is not None else None,
                         "currency": inv.currency if inv else None,
                         "invoice_date": inv.invoice_date.isoformat() if inv and inv.invoice_date else None,
                         "document_id": str(doc.id) if doc else None, "filename": doc.filename if doc else None,
                         "file_type": doc.file_type if doc else None, "location": inv.location if inv else None}
        out.append(CrossCheckOut(id=c.id, kind=c.kind, status=c.status, differences=c.differences or [],
                                 created_at=c.created_at, a=side["a"], b=side["b"]))
    return out
