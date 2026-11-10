# Setup and deployment

## Run everything on one machine (Docker)

Requirements: Docker with Compose v2, an OpenAI API key, Node.js 20+ for the web app.

```bash
git clone <this repository> docintel && cd docintel
cp .env.example .env            # set OPENAI_API_KEY (AI_PROVIDER=openai is the default)
docker compose up -d --build    # API, 2 workers, PostgreSQL + pgvector, Redis
curl http://localhost:8000/api/v1/health
```

API documentation: http://localhost:8000/api/docs

Web app:

```bash
cd frontend
cp .env.example .env.local      # BACKEND_ORIGIN=http://localhost:8000
npm install
npm run dev                     # http://localhost:3000
```

Leave `ACCESS_CODES` empty for a local run (open mode), or set one and enter it in the app.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `AI_PROVIDER` | `openai` (`.env.example`) | `openai` = direct with `OPENAI_API_KEY`; `n8n` = through the AI gateway webhook; `fake` = tests only |
| `OPENAI_API_KEY` |  | for `AI_PROVIDER=openai` |
| `AI_GATEWAY_URL`, `AI_GATEWAY_KEY` |  | for `AI_PROVIDER=n8n` (see [n8n/README.md](../n8n/README.md)) |
| `EXTRACTION_MODEL`, `VISION_MODEL` | `gpt-4.1-mini` | models for text and image readings |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | semantic search vectors (1536 dimensions) |
| `AI_CONCURRENCY` | `4` | parallel AI calls inside one document |
| `AI_DAILY_CALL_LIMIT` | `3000` | daily safety budget for AI calls |
| `AI_CACHE` | `true` | reuse AI answers for identical input (resumable jobs, no repeated cost) |
| `ACCESS_CODES` |  | comma-separated access codes; empty = open |
| `CORS_ORIGINS` | `http://localhost:3000` | only needed when a browser calls the API directly |
| `MAX_FILE_MB`, `MAX_FILES_PER_UPLOAD`, `MAX_PAGES` | `50`, `50`, `1500` | upload limits |
| `OCR_DPI` | `300` | rendering resolution for scanned PDF pages |
| `RECOVERY_STALE_MINUTES` | `15` | a processing document with no heartbeat for this long is requeued |
| `POSTGRES_PASSWORD` | `docintel` | database password |

Web app (`frontend/.env.local` or Vercel project settings):

| Variable | Meaning |
|---|---|
| `BACKEND_ORIGIN` | address of the API server; Vercel forwards `/api/*` there (never sent to browsers) |
| `NEXT_PUBLIC_PREPARED_FOR` | optional label ("Prepared for …") |
| `NEXT_PUBLIC_REPO_URL` | optional link to the repository |

## Production deployment (as used for the demo)

**Processing server** (any Linux VM with Docker and a Traefik reverse proxy):

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --build
```

The server overlay adds the HTTPS router for the API (`API_HOST`), removes public database and Redis ports, puts
everything on private networks, and sets hard CPU and memory limits on every container (API 0.5 CPU / 512 MB, each
worker 0.6 CPU / 640 MB, PostgreSQL 0.5 / 512 MB, Redis 0.25 / 192 MB). Workers get a 2-minute grace period to
finish the current document on restart.

`deploy/deploy_server.sh` syncs the code and restarts the stack (`… test` also runs the full test suite inside the
server). `deploy/run_eval_server.sh` runs a measured evaluation from a clean state. Server address and SSH key come
from a local, uncommitted file (`~/.config/docintel/server.env`).

**Web app** (Vercel):

```bash
cd frontend
vercel link
vercel env add BACKEND_ORIGIN production       # https://<api-host>
vercel deploy --prod
```

**AI gateway** (n8n): `python3 n8n/build_gateway.py` creates or updates the workflow and stores its header key
locally. Credentials are never committed.

## Repository layout

```
backend/            FastAPI app, pipeline, workers, tests, Dockerfile
  app/api/          REST endpoints (documents, invoices, search, export, system)
  app/pipeline/     detect, readers (PDF/OCR), spreadsheets, segment, extract, evidence, validate, matching, runner
  app/ai/           AI client (n8n / OpenAI / fake) and the prompts
  tests/            pytest suite (unit, readers/OCR, API, failures, operations)
frontend/           Next.js web app (Vercel)
dataset/            labelled dataset generator (+ sample files)
evaluation/         evaluation script, results and history of runs
n8n/                AI gateway workflow (export + build script)
deploy/             production overlay and scripts
docs/               this documentation
```
