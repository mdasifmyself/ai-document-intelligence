# Operations, failure handling and recovery

## How failures are handled automatically

| Situation | What the system does | What a person sees |
|---|---|---|
| Broken, empty, renamed or unsupported file | Detected from the bytes before any reader runs; document fails with a stable code (`CORRUPTED_FILE`, `EMPTY_FILE`, `UNSUPPORTED_TYPE`) | Red box with the reason and **What to do** |
| Password-protected PDF | `PASSWORD_PROTECTED` | "Upload an unlocked copy" |
| One damaged page in a long PDF | The page is skipped with a warning; the rest is processed | "Damaged page" note |
| Truncated image | Read as far as possible, with a warning | "Damaged file: results may be incomplete" |
| Poor scan | Image clean-up, second OCR pass, second independent reading from the page image | Uncertain values flagged for review |
| AI service slow or failing | Retries with exponential backoff (timeouts, 429, 5xx); then `AI_UNAVAILABLE` | Retry with one click (or "Retry all failed") |
| AI budget used up | Calls stop for the day (`AI_DAILY_CALL_LIMIT`) | Clear message; retry later |
| Semantic index cannot be built | Document still completes; keyword search works | Note in the processing history |
| Job takes too long | RQ timeout (2 h) + failure callback marks `JOB_TIMEOUT` | Retry; split very large files |
| Worker crashes, is killed or the server restarts | The recovery sweeper (every 2 minutes) finds documents whose worker is gone and requeues them (up to 3 attempts, then `WORKER_LOST`). Finished AI work is reused from the answer cache. | "Put back in the queue automatically" in the history; *System health* lists it |
| Queue lost (Redis restart) | Documents still "Waiting" with no job are requeued | Recovery note |
| Deploy / restart | Workers finish their current document first (2-minute grace period) | Usually nothing |
| Browser loses the API briefly | Reads retry automatically (0.6 s, 1.5 s, 3.5 s); one calm "Reconnecting…" banner | Banner disappears when the server answers |

## Runbook

| Symptom | Check | Action |
|---|---|---|
| Files stay "Waiting" | *System health* → Workers | No worker running: `docker compose ... up -d worker` (or restart the stack). |
| Many `AI_UNAVAILABLE` failures | *System health* → AI service (last error) | Wait until the AI answers again, then **Retry the retryable ones**. Check the gateway workflow is active and the provider is reachable. |
| A file shows no progress | *System health* → Slow or stuck | Nothing: it is requeued automatically within minutes. To force it, open the file and press *Process again*. |
| Wrong value on an invoice | Document detail → proof quote and page image | *Edit* → save (checks re-run) → *Approve*. |
| Need to re-run everything after a prompt change | — | *Process again* on the documents (the prompt version is part of the cache key, so new answers are fetched). |
| Disk filling up | `docker system df`, `du -sh /var/lib/docker/volumes/docintel_files` | Delete old documents through the API or UI (files are removed with them). |

## Monitoring endpoints

* `GET /api/v1/health`: database and queue reachability (for uptime monitors).
* `GET /api/v1/system/status`: workers, backlog, AI state and budget, stuck documents, failures by code, recent
  failures and recoveries (the *System health* page).
* `GET /api/v1/jobs/queue`: queue depth and counts by status.

## Backlog management

* The queue absorbs bursts: uploads return immediately, workers process in order.
* *Documents → In progress* and *System health → Backlog* show what is waiting.
* Add workers to clear a backlog faster (`replicas`), or raise `AI_CONCURRENCY` when the AI provider allows more.
* Failed jobs never block the queue; they wait in *Failed* until retried or deleted.

## How these paths are tested

`backend/tests/test_failures.py` and `test_ops.py` cover broken files, unsupported and oversized uploads, AI outage
then reprocessing, AI retry and give-up behaviour, the failure callback (timeout), the recovery sweeper (requeue and
give-up after 3 attempts), Excel export and the system status endpoint. A live crash-recovery test (killing a worker
in the middle of the 1,000-page batch) is described in [08-evaluation-report.md](08-evaluation-report.md).
