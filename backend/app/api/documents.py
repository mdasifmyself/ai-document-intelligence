"""Upload, list, inspect, reprocess and delete documents."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..models import Document, Invoice, ProcessingEvent, ValidationIssue
from ..pipeline.detect import ALLOWED_EXTENSIONS, ProcessingError
from ..pipeline.readers import page_image
from ..queue import enqueue_document
from ..schemas import DocumentDetail, DocumentOut, EventOut, InvoiceDetail, IssueOut, Page, PageOut, StatusOut, UploadResult
from ..security import rate_limit, require_access
from ..storage import TooLarge, save_upload

router = APIRouter(prefix="/documents", tags=["Documents"], dependencies=[Depends(require_access)])


def _safe_name(name: str | None) -> str:
    base = Path(name or "file").name.replace("\x00", "")
    return base[:200] or "file"


def get_doc(db: Session, doc_id: uuid.UUID) -> Document:
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    return doc


def document_detail(db: Session, doc: Document) -> DocumentDetail:
    db.refresh(doc)
    invoices = db.scalars(select(Invoice).where(Invoice.document_id == doc.id)
                          .options(selectinload(Invoice.issues), selectinload(Invoice.corrections))
                          .order_by(Invoice.seq)).all()
    doc_issues = db.scalars(select(ValidationIssue).where(ValidationIssue.document_id == doc.id,
                                                          ValidationIssue.invoice_id.is_(None))).all()
    pages = [PageOut(page_no=p.page_no, label=p.label, method=p.method, ocr_confidence=p.ocr_confidence,
                     rotation=p.rotation, deskew_angle=p.deskew_angle, chars=len(p.text or "")) for p in doc.pages]
    out = DocumentDetail.model_validate(doc, from_attributes=True)
    out.pages = pages
    out.invoices = [InvoiceDetail.model_validate(i, from_attributes=True).model_copy(
        update={"document_filename": doc.filename, "document_file_type": doc.file_type}) for i in invoices]
    out.issues = [IssueOut.model_validate(i, from_attributes=True) for i in doc_issues]
    out.events = [EventOut.model_validate(e, from_attributes=True) for e in list(doc.events)[-200:]]
    return out


@router.post("", response_model=UploadResult, status_code=202, summary="Upload one or more files",
             dependencies=[rate_limit("upload", get_settings().uploads_per_minute)])
def upload(files: list[UploadFile] = File(..., description="PDF, JPG, PNG, TIFF, XLSX, XLS or CSV"),
           db: Session = Depends(get_db)):
    """Files are saved and queued at once (HTTP 202). Processing runs in the background; poll
    `GET /documents/{id}/status` or the list endpoint to follow progress."""
    s = get_settings()
    if len(files) > s.max_files_per_upload:
        raise HTTPException(413, f"At most {s.max_files_per_upload} files per upload.")
    batch_id = uuid.uuid4()
    accepted, rejected, new_docs = [], [], []
    for f in files:
        name = _safe_name(f.filename)
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            rejected.append({"filename": name, "code": "UNSUPPORTED_TYPE",
                             "message": f"{ext or 'This file type'} is not supported. Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV."})
            continue
        try:
            path, size, digest = save_upload(f)
        except TooLarge:
            rejected.append({"filename": name, "code": "FILE_TOO_LARGE", "message": f"Larger than {s.max_file_mb} MB."})
            continue
        doc = Document(filename=name, size_bytes=size, sha256=digest, storage_path=str(path), batch_id=batch_id,
                       status="queued", progress={"stage": "queued", "done": 0, "total": 0})
        db.add(doc)
        new_docs.append(doc)
    db.commit()
    for doc in new_docs:
        db.add(ProcessingEvent(document_id=doc.id, stage="upload", status="completed",
                               message=f"Uploaded ({doc.size_bytes:,} bytes) and queued."))
    db.commit()
    for doc in new_docs:
        enqueue_document(doc.id)
        db.refresh(doc)
        accepted.append(DocumentOut.model_validate(doc, from_attributes=True))
    return UploadResult(batch_id=batch_id, accepted=accepted, rejected=rejected)


@router.get("", response_model=Page, summary="List documents")
def list_documents(status: str | None = Query(None, description="Comma list: queued,processing,completed,needs_review,failed"),
                   file_type: str | None = None, q: str | None = Query(None, description="Keyword in file name or text"),
                   batch_id: uuid.UUID | None = None, ids: str | None = Query(None, description="Comma list of ids"),
                   page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), db: Session = Depends(get_db)):
    stmt = select(Document)
    if status:
        stmt = stmt.where(Document.status.in_([x.strip() for x in status.split(",")]))
    if file_type:
        stmt = stmt.where(Document.file_type.in_([x.strip() for x in file_type.split(",")]))
    if batch_id:
        stmt = stmt.where(Document.batch_id == batch_id)
    if ids:
        stmt = stmt.where(Document.id.in_([uuid.UUID(x) for x in ids.split(",") if x.strip()]))
    if q:
        stmt = stmt.where(or_(Document.filename.ilike(f"%{q}%"),
                              Document.text_tsv.op("@@")(func.websearch_to_tsquery("simple", q))))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[DocumentOut.model_validate(r, from_attributes=True) for r in rows], total=total or 0,
                page=page, page_size=page_size)


@router.get("/{doc_id}", response_model=DocumentDetail, summary="Everything about one document")
def get_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    return document_detail(db, get_doc(db, doc_id))


@router.get("/{doc_id}/status", response_model=StatusOut, summary="Lightweight processing status")
def get_status(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    d = get_doc(db, doc_id)
    return StatusOut(id=d.id, status=d.status, progress=d.progress or {}, invoice_count=d.invoice_count,
                     issue_count=d.issue_count, error_code=d.error_code, processing_ms=d.processing_ms)


@router.get("/{doc_id}/file", summary="Download the original file")
def get_file(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    d = get_doc(db, doc_id)
    return FileResponse(d.storage_path, filename=d.filename, media_type=d.mime or "application/octet-stream")


@router.get("/{doc_id}/pages/{page_no}", summary="Text of one page or sheet")
def get_page(doc_id: uuid.UUID, page_no: int, db: Session = Depends(get_db)):
    d = get_doc(db, doc_id)
    page = next((p for p in d.pages if p.page_no == page_no), None)
    if not page:
        raise HTTPException(404, "Page not found.")
    return {"page_no": page.page_no, "label": page.label, "method": page.method, "text": page.text,
            "ocr_confidence": page.ocr_confidence}


@router.get("/{doc_id}/pages/{page_no}/image", summary="Preview image of one page (PDF and images)",
            responses={200: {"content": {"image/png": {}}}})
def get_page_image(doc_id: uuid.UUID, page_no: int, db: Session = Depends(get_db)):
    d = get_doc(db, doc_id)
    if d.file_type not in ("pdf", "image"):
        raise HTTPException(400, "Previews exist for PDFs and images only.")
    cache = Path(get_settings().storage_dir) / "previews" / f"{d.id}-{page_no}.png"
    if not cache.exists():
        try:
            img = page_image(Path(d.storage_path), d.file_type, page_no, dpi=110)
        except ProcessingError as e:
            raise HTTPException(404 if e.code == "NOT_FOUND" else 422, e.message)
        cache.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(cache, "PNG", optimize=True)
    return Response(cache.read_bytes(), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/{doc_id}/reprocess", response_model=StatusOut, summary="Run the document again")
def reprocess(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Re-runs the full pipeline (useful after a failure such as the AI service being unavailable).
    Earlier results and manual corrections of this document are replaced."""
    d = get_doc(db, doc_id)
    if d.status == "processing":
        raise HTTPException(409, "The document is being processed right now.")
    d.status, d.progress = "queued", {"stage": "queued", "done": 0, "total": 0}
    db.add(ProcessingEvent(document_id=d.id, stage="reprocess", status="info", message="Reprocessing requested."))
    db.commit()
    enqueue_document(d.id)
    db.refresh(d)
    return StatusOut(id=d.id, status=d.status, progress=d.progress, invoice_count=d.invoice_count,
                     issue_count=d.issue_count, error_code=d.error_code, processing_ms=d.processing_ms)


@router.delete("/{doc_id}", status_code=204, summary="Delete a document and its results")
def delete_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    d = get_doc(db, doc_id)
    path = Path(d.storage_path)
    db.delete(d)
    db.commit()
    path.unlink(missing_ok=True)
    for p in (Path(get_settings().storage_dir) / "previews").glob(f"{doc_id}-*.png"):
        p.unlink(missing_ok=True)
    return Response(status_code=204)


jobs = APIRouter(prefix="/jobs", tags=["Jobs"], dependencies=[Depends(require_access)])


@jobs.get("/failed", response_model=Page, summary="Documents whose processing failed")
def failed(db: Session = Depends(get_db), page: int = 1, page_size: int = 50):
    stmt = select(Document).where(Document.status == "failed")
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[DocumentOut.model_validate(r, from_attributes=True) for r in rows], total=total or 0,
                page=page, page_size=page_size)


@jobs.post("/reprocess-failed", summary="Re-queue every failed document")
def reprocess_failed(db: Session = Depends(get_db), codes: str | None = Query(None, description="Only these error codes")):
    stmt = select(Document).where(Document.status == "failed")
    if codes:
        stmt = stmt.where(Document.error_code.in_([c.strip() for c in codes.split(",")]))
    docs = db.scalars(stmt.limit(200)).all()
    for d in docs:
        d.status, d.progress = "queued", {"stage": "queued", "done": 0, "total": 0}
        db.add(ProcessingEvent(document_id=d.id, stage="reprocess", status="info", message="Bulk reprocess of failed jobs."))
    db.commit()
    for d in docs:
        enqueue_document(d.id)
    return {"requeued": len(docs), "ids": [str(d.id) for d in docs]}


@jobs.get("/queue", summary="Queue and worker status")
def queue_status(db: Session = Depends(get_db)):
    from ..queue import queue_depth
    counts = dict(db.execute(text("SELECT status, count(*) FROM documents GROUP BY status")).all())
    return {"waiting_in_queue": queue_depth(), "processing": counts.get("processing", 0), "by_status": counts}
