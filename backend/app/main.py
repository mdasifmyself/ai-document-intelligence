"""DocIntel API."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .api import documents, export, invoices, search, system
from .config import get_settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DESCRIPTION = """
**DocIntel** reads invoices, receipts, scans, photos, Excel and CSV files, extracts the invoice data with AI,
checks every number, flags what needs a person, and makes everything searchable.

**How to use the API**
1. `POST /api/v1/documents` with one or more files (multipart field `files`). You get document ids back at once.
2. Poll `GET /api/v1/documents/{id}/status` until the status is `completed`, `needs_review` or `failed`.
3. Read results with `GET /api/v1/documents/{id}` (pages, invoices, validation issues, history).
4. Fix values with `PATCH /api/v1/invoices/{id}`; approve with `POST /api/v1/invoices/{id}/approve`.
5. Search with `GET /api/v1/search?q=...&mode=hybrid`.

Send the access code in the `X-Access-Code` header.
"""

TAGS = [
    {"name": "Documents", "description": "Upload files, follow processing, inspect results, reprocess, delete."},
    {"name": "Invoices", "description": "Extracted invoices: filter, correct values, approve after review."},
    {"name": "Search", "description": "Keyword, semantic and hybrid search; cross-document checks."},
    {"name": "Jobs", "description": "Failed jobs and the processing queue."},
    {"name": "Export", "description": "Download results as a formatted Excel workbook."},
    {"name": "System", "description": "Health, backlog, recovery, limits, dashboard numbers, sample files."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if get_settings().ai_provider != "fake":
        from .recovery import start_background_sweeper
        start_background_sweeper()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="DocIntel API", version=s.version, description=DESCRIPTION, openapi_tags=TAGS,
                  lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_origin_regex=r"https://.*\.vercel\.app",
                       allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Content-Disposition"])

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    for r in (documents.router, documents.jobs, invoices.router, search.router, export.router, system.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/api/docs")

    @app.get("/docs", include_in_schema=False)
    def old_docs():
        return RedirectResponse("/api/docs")

    return app


app = create_app()
