"""Automatic recovery: nothing stays stuck.

1. on_job_failure  – RQ calls it when a job crashes or times out; the document is marked failed with a clear code.
2. sweep           – runs every 2 minutes in the API process:
   • a document "processing" with no heartbeat for STALE_MINUTES (worker killed, server restarted)
     is put back in the queue (up to MAX_ATTEMPTS), otherwise marked failed (WORKER_LOST);
   • a document "queued" whose job vanished from Redis (e.g. Redis restarted) is queued again.
Every action is written to the document's processing history.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, text

from .db import session_scope
from .models import Document, ProcessingEvent, ValidationIssue

log = logging.getLogger("docintel.recovery")
from .config import get_settings

STALE_MINUTES = get_settings().recovery_stale_minutes
LOST_QUEUE_MINUTES = 10
MAX_ATTEMPTS = 3
ORPHAN_MINUTES = 3          # processing, no live worker holds the job, and no heartbeat for this long


def _now():
    return datetime.now(timezone.utc)


def on_job_failure(job, connection, exc_type, exc_value, tb):
    """RQ failure callback (runs in the worker)."""
    try:
        import uuid
        doc_id = uuid.UUID(str(job.args[0]))
        timeout = exc_type is not None and "Timeout" in exc_type.__name__
        code = "JOB_TIMEOUT" if timeout else "WORKER_ERROR"
        msg = ("Processing took longer than the time limit and was stopped." if timeout
               else "The background worker stopped unexpectedly while processing this file.")
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            if doc and doc.status in ("queued", "processing"):
                doc.status, doc.error_code, doc.error_message = "failed", code, msg
                doc.finished_at = _now()
                doc.progress = {"stage": "failed", "done": 0, "total": 0}
                s.add(ValidationIssue(document_id=doc_id, code=code, severity="error", message=msg))
                s.add(ProcessingEvent(document_id=doc_id, stage="recovery", status="failed",
                                      message=f"{code}: {msg} You can process it again."))
    except Exception:
        log.exception("failure callback could not update the document")


def _jobs_held_by_workers() -> set[str] | None:
    """Job ids that live workers are working on right now (None if Redis is unreachable)."""
    try:
        from rq import Worker
        from .queue import redis_conn
        return {w.get_current_job_id() or "" for w in Worker.all(connection=redis_conn())}
    except Exception:
        return None


def _registries():
    """Job ids waiting/running, and ids of jobs RQ gave up on. cleanup=False: registry clean-up (which runs
    failure callbacks with signal-based timeouts) must only happen in the worker's main thread, not here."""
    from rq import Queue
    from rq.registry import FailedJobRegistry, StartedJobRegistry
    from .queue import QUEUE_NAME, redis_conn
    q = Queue(QUEUE_NAME, connection=redis_conn())
    alive = set(q.job_ids) | set(StartedJobRegistry(queue=q).get_job_ids(cleanup=False))
    dead = set(FailedJobRegistry(queue=q).get_job_ids(cleanup=False))
    return alive, dead


def sweep() -> dict:
    """One recovery pass. Returns what it did (also shown on the System page)."""
    from .queue import enqueue_document
    done = {"requeued": 0, "failed": 0, "lost_requeued": 0}
    now = _now()
    with session_scope() as s:
        got = s.execute(text("SELECT pg_try_advisory_xact_lock(515151)")).scalar()
        if not got:
            return done  # another API process is sweeping
        try:
            alive, dead = _registries()
        except Exception:
            alive, dead = None, set()
            log.warning("queue check skipped (Redis unavailable)")
        stale = s.scalars(select(Document).where(
            Document.status == "processing",
            or_(Document.heartbeat_at < now - timedelta(minutes=STALE_MINUTES),
                Document.heartbeat_at.is_(None) & (Document.started_at < now - timedelta(minutes=STALE_MINUTES))))).all()
        # a worker that died mid-job (killed, out of memory, restarted): RQ marks the job abandoned -> requeue now
        processing = s.scalars(select(Document).where(Document.status == "processing")).all()
        owned = _jobs_held_by_workers()
        orphaned = [d for d in processing
                    if owned is not None and not any(j.startswith(f"doc-{d.id}-") for j in owned)
                    and d.heartbeat_at is not None and d.heartbeat_at < now - timedelta(minutes=ORPHAN_MINUTES)]
        stale = list({d.id: d for d in [*stale, *orphaned]}.values())
        requeue = []
        for d in stale:
            if (d.attempts or 0) < MAX_ATTEMPTS:
                d.status, d.progress = "queued", {"stage": "queued", "done": 0, "total": 0}
                s.add(ProcessingEvent(document_id=d.id, stage="recovery", status="info",
                                      message="The worker processing this file stopped (restart or crash); the document "
                                              "was put back in the queue automatically. Finished AI work is reused."))
                requeue.append(d.id)
                done["requeued"] += 1
            else:
                msg = f"The worker stopped responding {MAX_ATTEMPTS} times while processing this file."
                d.status, d.error_code, d.error_message = "failed", "WORKER_LOST", msg
                d.finished_at = now
                s.add(ValidationIssue(document_id=d.id, code="WORKER_LOST", severity="error", message=msg))
                s.add(ProcessingEvent(document_id=d.id, stage="recovery", status="failed", message=msg))
                done["failed"] += 1
        try:
            if alive is None:
                raise RuntimeError("no queue")
            in_queue = alive
            waiting = s.scalars(select(Document).where(Document.status == "queued",
                                                       Document.created_at < now - timedelta(minutes=LOST_QUEUE_MINUTES))).all()
            for d in waiting:
                if d.id in requeue or any(j.startswith(f"doc-{d.id}-") for j in in_queue):
                    continue
                s.add(ProcessingEvent(document_id=d.id, stage="recovery", status="info",
                                      message="The queued job was missing from the queue; it was queued again."))
                requeue.append(d.id)
                done["lost_requeued"] += 1
        except Exception:
            log.warning("queue check skipped (Redis unavailable)")
    for doc_id in requeue:
        try:
            enqueue_document(doc_id)
        except Exception:
            log.exception("could not re-enqueue %s", doc_id)
    if any(done.values()):
        log.info("recovery sweep: %s", done)
    return done


def start_background_sweeper(interval_s: int = 120):
    def loop():
        time.sleep(20)
        while True:
            try:
                result = sweep()
                try:
                    from .queue import redis_conn
                    import json
                    redis_conn().set("docintel:last_sweep", json.dumps({"at": _now().isoformat(), **result}), ex=3600)
                except Exception:
                    pass
            except Exception:
                log.exception("recovery sweep failed")
            time.sleep(interval_s)
    threading.Thread(target=loop, name="recovery-sweeper", daemon=True).start()
