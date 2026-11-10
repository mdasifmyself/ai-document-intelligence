"""Background job queue (Redis + RQ). Slow OCR and AI work never blocks an API request."""
from redis import Redis
from rq import Callback, Queue

from .config import get_settings

QUEUE_NAME = "documents"
JOB_TIMEOUT = 2 * 60 * 60  # a 1,000-page scanned PDF can take a while on a small server

_sync_mode = False


def set_sync_mode(on: bool):
    """Tests run jobs inline instead of through Redis."""
    global _sync_mode
    _sync_mode = on


def redis_conn() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def enqueue_document(doc_id) -> str | None:
    if _sync_mode:
        from .pipeline.runner import process_document
        process_document(str(doc_id))
        return None
    q = Queue(QUEUE_NAME, connection=redis_conn(), default_timeout=JOB_TIMEOUT)
    from .recovery import on_job_failure
    job = q.enqueue("app.pipeline.runner.process_document", str(doc_id), job_id=f"doc-{doc_id}-{_suffix()}",
                    result_ttl=3600, failure_ttl=7 * 86400, on_failure=Callback(on_job_failure))
    return job.id


def queue_depth() -> int:
    try:
        return Queue(QUEUE_NAME, connection=redis_conn()).count
    except Exception:
        return -1


def _suffix() -> str:
    import secrets
    return secrets.token_hex(3)
