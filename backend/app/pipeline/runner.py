"""The background job: one document from upload to searchable, checked data.

Stages (each one is written to processing_events with its duration):
  detect -> read (text / OCR / sheets) -> split -> extract (AI, in parallel) -> validate
  -> match (duplicates, cross-checks) -> index (semantic vectors) -> done
Any known failure stops the document with a clear error code; it can be reprocessed later.
"""
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, update

from ..ai import client
from ..ai.client import AIUnavailable
from ..config import get_settings
from ..db import session_scope
from ..models import Document, DocumentPage, Invoice, ProcessingEvent, ValidationIssue
from . import extract as ex
from .detect import ProcessingError, detect
from .matching import refresh_document, refresh_invoice, run_matching
from .normalize import normalize_invoice_number, normalize_name
from .readers import page_image, read_image, read_pdf
from .segment import split_invoices
from .spreadsheets import read_spreadsheet
from .types import CORE_FIELDS, ExtractedInvoice
from .validate import Issue, validate

log = logging.getLogger("docintel.runner")


def _now():
    return datetime.now(timezone.utc)


class Tracker:
    """Writes progress and history in short transactions so the UI sees them live."""

    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.t0 = time.monotonic()
        self._stage_t = {}

    def progress(self, stage: str, done: int = 0, total: int = 0):
        with session_scope() as s:
            s.execute(update(Document).where(Document.id == self.doc_id)
                      .values(progress={"stage": stage, "done": done, "total": total}, heartbeat_at=_now()))

    def start(self, stage: str, message: str | None = None):
        self._stage_t[stage] = time.monotonic()
        self.progress(stage)
        self.event(stage, "started", message)

    def done(self, stage: str, message: str | None = None):
        ms = int((time.monotonic() - self._stage_t.get(stage, time.monotonic())) * 1000)
        self.event(stage, "completed", message, ms)

    def event(self, stage, status, message=None, duration_ms=None):
        with session_scope() as s:
            s.add(ProcessingEvent(document_id=self.doc_id, stage=stage, status=status,
                                  message=message, duration_ms=duration_ms))


def _search_text(inv: Invoice) -> str:
    items = "; ".join(i.get("description", "") for i in (inv.line_items or [])[:30])
    parts = [f"Invoice {inv.invoice_number or ''}", f"from {inv.supplier_name or 'unknown supplier'}",
             f"to {inv.customer_name or 'unknown customer'}",
             f"dated {inv.invoice_date.isoformat() if inv.invoice_date else 'unknown'}",
             f"total {inv.total if inv.total is not None else 'unknown'} {inv.currency or ''}", f"Items: {items}"]
    return ". ".join(parts)


def _to_row(doc_id, seq: int, e: ExtractedInvoice) -> Invoice:
    def f(n, limit=None):
        v = e.get(n)
        return v[:limit] if limit and isinstance(v, str) else v
    conf = [v.confidence for k, v in e.fields.items() if k in CORE_FIELDS and v.value is not None]
    inv = Invoice(
        document_id=doc_id, seq=seq, source_kind=e.source_kind, location=e.location,
        invoice_number=f("invoice_number", 100), invoice_date=f("invoice_date"),
        supplier_name=f("supplier_name", 255), customer_name=f("customer_name", 255),
        subtotal=f("subtotal"), tax=f("tax"), total=f("total"), currency=f("currency"),
        line_items=e.line_items, fields={k: v.as_dict() for k, v in e.fields.items()},
        extraction_method=e.method, model=e.model, confidence=round(sum(conf) / len(conf), 3) if conf else 0.0,
        raw_ai_output=e.raw,
    )
    inv.invoice_number_norm = normalize_invoice_number(inv.invoice_number)
    inv.supplier_norm = normalize_name(inv.supplier_name)
    inv.search_text = _search_text(inv)
    return inv


def _save_issues(s, doc_id, inv: Invoice | None, issues: list[Issue]):
    for i in issues:
        s.add(ValidationIssue(document_id=doc_id, invoice_id=inv.id if inv else None, code=i.code,
                              severity=i.severity, field=i.field, message=i.message, details=i.details))


def _reset(doc_id):
    with session_scope() as s:
        s.execute(delete(Invoice).where(Invoice.document_id == doc_id))
        s.execute(delete(ValidationIssue).where(ValidationIssue.document_id == doc_id))
        s.execute(delete(DocumentPage).where(DocumentPage.document_id == doc_id))
        doc = s.get(Document, doc_id)
        doc.status, doc.error_code, doc.error_message = "processing", None, None
        doc.started_at, doc.finished_at, doc.processing_ms = _now(), None, None
        doc.heartbeat_at = _now()
        doc.attempts = (doc.attempts or 0) + 1
        doc.invoice_count, doc.issue_count, doc.ai_calls = 0, 0, 0
        doc.progress = {"stage": "starting", "done": 0, "total": 0}
        return Path(doc.storage_path), doc.filename


def _extract_all(segments, path: Path, file_type: str, tracker: Tracker) -> list[ExtractedInvoice]:
    """Text PDFs: one AI reading of the text. Scans and photos (up to 3 pages per invoice): two independent
    readings, OCR text and page image, reconciled field by field."""
    s = get_settings()
    jobs = []
    for seg in segments:
        ocr = any(p.method == "ocr" for p in seg.pages)
        mode = "dual" if (ocr and s.vision_fallback and len(seg.pages) <= 3) else "text"
        images = None
        if mode == "dual":  # rendered here, in one thread: the PDF library is not thread-safe
            images = [page_image(path, file_type, n, dpi=170) for n in seg.page_numbers[:3]]
        jobs.append((seg, mode, images))

    def run(job):
        seg, mode, images = job
        if mode == "text":
            return ex.extract_segment(seg, None)
        ocr_conf = ex._page_confidence(seg)
        loc = {"pages": seg.page_numbers}
        text_inv = None
        if sum(len(p.text.strip()) for p in seg.pages) >= 40:
            data, model = ex.ask_model(seg.text)
            text_inv = ex.build_invoice(data, seg.text, method="llm_text", model=model, location=loc,
                                        ocr_conf=ocr_conf, any_ocr=True)
        data, model = ex.ask_model(seg.text, images)
        image_inv = ex.build_invoice(data, seg.text, method="llm_vision", model=model, location=loc,
                                     ocr_conf=ocr_conf, any_ocr=True)
        return ex.reconcile(text_inv, image_inv) if text_inv is not None else image_inv

    results: list[ExtractedInvoice] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, s.ai_concurrency)) as pool:
        for r in pool.map(run, jobs):
            results.append(r)
            done += 1
            if done % 3 == 0 or done == len(jobs):
                tracker.progress("extracting", done, len(jobs))
    dual = sum(1 for _, m, _ in jobs if m == "dual")
    if dual:
        tracker.event("extract", "info", f"{dual} scanned invoice(s) read twice (OCR text and page image) and reconciled.")
    return results


def process_document(doc_id: str):
    """Entry point for the queue worker."""
    import uuid
    doc_id = uuid.UUID(str(doc_id))
    tracker = Tracker(doc_id)
    path, filename = _reset(doc_id)
    tracker.event("job", "started", "Processing started.")
    try:
        tracker.start("detect")
        d = detect(path, filename)
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            doc.file_type, doc.mime = d.file_type, d.mime
        tracker.done("detect", f"Detected {d.file_type.upper()} ({d.mime}).")

        doc_issues: list[Issue] = []
        extracted: list[ExtractedInvoice] = []
        tracker.start("read")
        if d.file_type in ("pdf", "image"):
            pages = read_pdf(path, tracker.progress) if d.file_type == "pdf" else read_image(path, tracker.progress)
            methods = {p.method for p in pages}
            text_method = "mixed" if {"digital", "ocr"} <= methods else ("ocr" if "ocr" in methods else "digital")
            ocr_confs = [p.ocr_confidence for p in pages if p.ocr_confidence is not None]
            for p in pages:
                for w in p.warnings:
                    doc_issues.append(Issue("DAMAGED_PAGE" if p.method == "error" else "DAMAGED_FILE", "warning",
                                            f"Page {p.page_no}: {w}"))
            if not any(p.text.strip() for p in pages):
                doc_issues.append(Issue("NO_TEXT_FOUND", "warning", "No readable text was found in this file."))
            tracker.done("read", f"{len(pages)} page(s) read ({text_method}).")
            tracker.start("split")
            segments = [sg for sg in split_invoices(pages) if any(p.text.strip() for p in sg.pages)
                        or ex.needs_vision(sg)]
            tracker.done("split", f"{len(segments)} invoice(s) found.")
            tracker.start("extract")
            extracted = _extract_all(segments, path, d.file_type, tracker) if segments else []
            ai_calls = len(segments)
            tracker.done("extract", f"{len(extracted)} invoice(s) extracted with AI.")
        else:
            sheet = read_spreadsheet(path, d.file_type)
            pages, text_method = sheet.pages, "spreadsheet"
            ocr_confs = []
            tracker.done("read", f"{len(pages)} sheet(s) read; {len(sheet.records)} row(s) mapped from columns.")
            tracker.start("extract")
            extracted = list(sheet.records)
            for sheet_no, name, text in sheet.layout_sheets:
                extracted.append(ex.extract_layout_sheet(sheet_no, name, text))
            ai_calls = len(sheet.layout_sheets)
            if not extracted:
                doc_issues.append(Issue("NO_INVOICE_DATA", "warning",
                                        "No invoice columns or invoice-like sheets were found in this spreadsheet."))
            tracker.done("extract", f"{len(extracted)} record(s) extracted.")

        with session_scope() as s:
            doc = s.get(Document, doc_id)
            doc.page_count = len(pages)
            doc.text_method = text_method
            doc.ocr_confidence = round(sum(ocr_confs) / len(ocr_confs), 1) if ocr_confs else None
            doc.full_text = "\n\n".join(p.text for p in pages)[:2_000_000]
            doc.ai_calls = ai_calls
            s.add_all([DocumentPage(document_id=doc_id, page_no=p.page_no, label=p.label, method=p.method,
                                    text=p.text, ocr_confidence=p.ocr_confidence, rotation=p.rotation,
                                    deskew_angle=p.deskew_angle) for p in pages])

        tracker.start("validate")
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            # identical file received before?
            earlier = s.query(Document).filter(Document.sha256 == doc.sha256, Document.id != doc.id,
                                               Document.created_at < doc.created_at).order_by(Document.created_at).first()
            if earlier:
                doc.duplicate_of = earlier.id
                doc_issues.append(Issue("DUPLICATE_FILE", "warning", f"This exact file was already uploaded as "
                                        f"\"{earlier.filename}\".", details={"other_document_id": str(earlier.id)}))
            _save_issues(s, doc_id, None, doc_issues)
            for seq, e in enumerate(extracted, start=1):
                inv = _to_row(doc_id, seq, e)
                s.add(inv)
                s.flush()
                _save_issues(s, doc_id, inv, validate(e))
            s.flush()
            s.refresh(doc)
            for inv in doc.invoices:
                refresh_invoice(s, inv)
        tracker.done("validate")

        tracker.start("match")
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            n = run_matching(s, doc)
            for inv in doc.invoices:
                refresh_invoice(s, inv)
        tracker.done("match", f"{n} cross-check(s) recorded.")

        tracker.start("index")
        try:
            with session_scope() as s:
                invs = s.query(Invoice).filter(Invoice.document_id == doc_id).all()
                if invs:
                    vectors = client.embed([i.search_text or "" for i in invs])
                    for inv, vec in zip(invs, vectors):
                        inv.embedding = vec
            tracker.done("index", "Semantic search index updated.")
        except AIUnavailable as e:
            tracker.event("index", "failed", f"Semantic index skipped: {e}. Keyword search still works.")

        with session_scope() as s:
            doc = s.get(Document, doc_id)
            doc.status = "completed"
            doc.finished_at = _now()
            doc.processing_ms = int((time.monotonic() - tracker.t0) * 1000)
            doc.progress = {"stage": "done", "done": 1, "total": 1}
            refresh_document(s, doc)
        tracker.event("job", "completed", "Processing finished.", int((time.monotonic() - tracker.t0) * 1000))

    except ProcessingError as e:
        _fail(doc_id, tracker, e.code, e.message)
    except AIUnavailable as e:
        _fail(doc_id, tracker, "AI_UNAVAILABLE", str(e))
    except Exception as e:  # unknown bug: keep the details in history, show a calm message
        log.exception("processing failed")
        detail = "".join(traceback.format_exception_only(type(e), e))[:600] + "\n" + traceback.format_exc()[-900:]
        _fail(doc_id, tracker, "INTERNAL_ERROR", "Something went wrong while processing this file.", detail)


def _fail(doc_id, tracker: Tracker, code: str, message: str, detail: str | None = None):
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        doc.status, doc.error_code, doc.error_message = "failed", code, message
        doc.finished_at = _now()
        doc.processing_ms = int((time.monotonic() - tracker.t0) * 1000)
        doc.progress = {"stage": "failed", "done": 0, "total": 0}
        s.add(ValidationIssue(document_id=doc_id, code=code, severity="error", message=message))
        doc.issue_count = 1
    tracker.event("job", "failed", f"{code}: {message}" + (f"\n{detail}" if detail else ""))
