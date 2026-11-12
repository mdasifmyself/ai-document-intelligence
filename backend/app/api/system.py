"""Health, limits, dashboard numbers and the built-in sample files."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..ai.prompts import PROMPT_VERSION
from ..config import get_settings
from ..db import get_db
from ..models import CrossCheck, Document, Invoice, ProcessingEvent, ValidationIssue
from ..pipeline.detect import ALLOWED_EXTENSIONS
from ..queue import enqueue_document, queue_depth, redis_conn
from ..schemas import DocumentOut, UploadResult
from ..security import rate_limit, require_access
from ..storage import copy_into_storage

router = APIRouter(tags=["System"])


@router.get("/health", summary="Is the service up?")
def health(db: Session = Depends(get_db)):
    s = get_settings()
    out = {"status": "ok", "version": s.version, "database": "ok", "queue": "ok", "ai_provider": s.ai_provider}
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        out["database"], out["status"] = "down", "degraded"
    try:
        redis_conn().ping()
    except Exception:
        out["queue"], out["status"] = "down", "degraded"
    return out


BUILD_FILE = Path(__file__).resolve().parents[1] / "BUILD_COMMIT"   # written by deploy/deploy_server.sh


def build_commit() -> str:
    """Git commit the running code was deployed from ("local" when run from a checkout)."""
    try:
        return BUILD_FILE.read_text().strip() or "local"
    except OSError:
        return "local"


@router.get("/meta", summary="Limits and configuration the UI needs")
def meta():
    s = get_settings()
    return {"app": s.app_name, "version": s.version, "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            "max_file_mb": s.max_file_mb, "max_files_per_upload": s.max_files_per_upload, "max_pages": s.max_pages,
            "extraction_model": s.extraction_model, "vision_model": s.vision_model,
            "embedding_model": s.embedding_model, "prompt_version": PROMPT_VERSION,
            "access_code_required": bool(s.access_code_list), "commit": build_commit()}


@router.get("/stats", summary="Numbers for the dashboard", dependencies=[Depends(require_access)])
def stats(db: Session = Depends(get_db)):
    by_status = dict(db.execute(text("SELECT status, count(*) FROM documents GROUP BY status")).all())
    by_type = dict(db.execute(text("SELECT coalesce(file_type,'unknown'), count(*) FROM documents GROUP BY 1")).all())
    inv_total = db.scalar(select(func.count(Invoice.id))) or 0
    inv_review = db.scalar(select(func.count(Invoice.id)).where(Invoice.needs_review.is_(True))) or 0
    inv_reviewed = db.scalar(select(func.count(Invoice.id)).where(Invoice.status == "reviewed")) or 0
    pages = db.scalar(select(func.coalesce(func.sum(Document.page_count), 0))) or 0
    avg_ms = db.scalar(select(func.avg(Document.processing_ms)).where(Document.status.in_(["completed", "needs_review"])))
    p95_ms = db.scalar(text("SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY processing_ms) FROM documents "
                            "WHERE status IN ('completed','needs_review')"))
    issues = db.execute(select(ValidationIssue.code, ValidationIssue.severity, func.count())
                        .where(ValidationIssue.severity != "info")
                        .group_by(ValidationIssue.code, ValidationIssue.severity).order_by(func.count().desc())).all()
    value = db.execute(select(Invoice.currency, func.sum(Invoice.total), func.count())
                       .where(Invoice.source_kind == "document").group_by(Invoice.currency)).all()
    checks = dict(db.execute(select(CrossCheck.status, func.count()).group_by(CrossCheck.status)).all())
    methods = dict(db.execute(select(Invoice.extraction_method, func.count()).group_by(Invoice.extraction_method)).all())
    recent = db.execute(text(
        "SELECT date_trunc('hour', created_at) AS h, count(*) FROM documents "
        "WHERE created_at > now() - interval '48 hours' GROUP BY 1 ORDER BY 1")).all()
    done = by_status.get("completed", 0) + by_status.get("needs_review", 0)
    finished = done + by_status.get("failed", 0)
    return {
        "documents": {"total": sum(by_status.values()), "by_status": by_status, "by_type": by_type,
                      "pages": int(pages), "success_rate": round(done / finished, 4) if finished else None},
        "invoices": {"total": inv_total, "needs_review": inv_review, "reviewed": inv_reviewed,
                     "by_method": methods},
        "processing": {"avg_ms": int(avg_ms) if avg_ms else None, "p95_ms": int(p95_ms) if p95_ms else None,
                       "waiting_in_queue": queue_depth(), "processing_now": by_status.get("processing", 0)},
        "issues": [{"code": c, "severity": s, "count": n} for c, s, n in issues],
        "value_by_currency": [{"currency": c or "unknown", "total": float(t or 0), "count": n} for c, t, n in value],
        "cross_checks": checks,
        "uploads_last_48h": [{"hour": h.isoformat(), "count": n} for h, n in recent],
    }


def _sample_files() -> list[Path]:
    folder = Path(get_settings().samples_dir)
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))


@router.get("/samples", summary="Sample files available for a one-click demo", dependencies=[Depends(require_access)])
def samples():
    return [{"name": p.name, "size_bytes": p.stat().st_size} for p in _sample_files()]


@router.post("/samples/load", response_model=UploadResult, status_code=202, summary="Process the sample set",
             dependencies=[Depends(require_access), rate_limit("samples", 3)])
def load_samples(db: Session = Depends(get_db)):
    files = _sample_files()
    if not files:
        raise HTTPException(404, "No sample files are installed on this server.")
    batch = uuid.uuid4()
    docs = []
    for p in files:
        path, size, digest = copy_into_storage(p)
        d = Document(filename=p.name, size_bytes=size, sha256=digest, storage_path=str(path), batch_id=batch,
                     status="queued", progress={"stage": "queued", "done": 0, "total": 0})
        db.add(d)
        docs.append(d)
    db.commit()
    for d in docs:
        db.add(ProcessingEvent(document_id=d.id, stage="upload", status="completed", message="Sample file queued."))
    db.commit()
    for d in docs:
        enqueue_document(d.id)
    for d in docs:
        db.refresh(d)
    return UploadResult(batch_id=batch, accepted=[DocumentOut.model_validate(d, from_attributes=True) for d in docs])


@router.get("/system/status", summary="Workers, backlog, failures and recovery", dependencies=[Depends(require_access)])
def system_status(db: Session = Depends(get_db)):
    """Everything an operator needs to see whether the system is healthy and what to do if not."""
    import json
    from datetime import datetime, timedelta, timezone

    from rq import Queue, Worker
    from rq.registry import FailedJobRegistry

    from ..queue import QUEUE_NAME
    from ..recovery import STALE_MINUTES

    now = datetime.now(timezone.utc)
    out: dict = {"checked_at": now.isoformat(), "queue": {}, "workers": [], "ai": {}, "recovery": None}
    try:
        conn = redis_conn()
        q = Queue(QUEUE_NAME, connection=conn)
        out["queue"] = {"waiting": q.count, "failed_jobs_in_registry": FailedJobRegistry(queue=q).count}
        out["workers"] = [{"name": w.name[:8], "state": w.get_state(),
                           "current_job": (w.get_current_job_id() or "")[:40] or None,
                           "last_heartbeat": w.last_heartbeat.isoformat() if w.last_heartbeat else None}
                          for w in Worker.all(connection=conn)]
        for kind in ("ok", "error"):
            v = conn.get(f"docintel:ai_last_{kind}")
            if v:
                at, _, detail = v.decode().partition("|")
                out["ai"][f"last_{kind}"] = {"at": at, "detail": detail}
        sweep = conn.get("docintel:last_sweep")
        out["recovery"] = json.loads(sweep) if sweep else None
        out["ai"]["calls_today"] = int(conn.get(f"docintel:ai_calls:{now.date().isoformat()}") or 0)
        out["ai"]["daily_limit"] = get_settings().ai_daily_call_limit
    except Exception as e:
        out["queue"] = {"error": f"Queue (Redis) unreachable: {type(e).__name__}"}
    stuck = db.scalars(select(Document).where(Document.status == "processing",
                                              Document.heartbeat_at < now - timedelta(minutes=5))).all()
    failed = db.scalars(select(Document).where(Document.status == "failed").order_by(Document.finished_at.desc().nulls_last())
                        .limit(10)).all()
    counts = dict(db.execute(text("SELECT coalesce(error_code,'?'), count(*) FROM documents WHERE status='failed' GROUP BY 1")).all())
    recovered = db.execute(select(ProcessingEvent.document_id, ProcessingEvent.message, ProcessingEvent.created_at)
                           .where(ProcessingEvent.stage == "recovery").order_by(ProcessingEvent.id.desc()).limit(10)).all()
    out["documents"] = {
        "slow_or_stuck": [{"id": str(d.id), "filename": d.filename, "stage": (d.progress or {}).get("stage"),
                           "last_sign_of_life": d.heartbeat_at.isoformat() if d.heartbeat_at else None} for d in stuck],
        "stale_after_minutes": STALE_MINUTES,
        "failed_by_code": counts,
        "recent_failures": [{"id": str(d.id), "filename": d.filename, "code": d.error_code, "message": d.error_message,
                             "attempts": d.attempts, "at": d.finished_at.isoformat() if d.finished_at else None} for d in failed],
        "recent_recoveries": [{"document_id": str(r[0]), "message": r[1], "at": r[2].isoformat()} for r in recovered],
    }
    return out
