"""API response and request shapes (they also drive the interactive docs at /docs)."""
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IssueOut(ORM):
    id: int
    invoice_id: UUID | None
    code: str
    severity: Literal["error", "warning", "info"]
    field: str | None
    message: str
    details: dict = {}


class CorrectionOut(ORM):
    id: int
    field: str
    old_value: Any
    new_value: Any
    reason: str | None
    corrected_by: str
    created_at: datetime


class EventOut(ORM):
    id: int
    stage: str
    status: str
    message: str | None
    duration_ms: int | None
    created_at: datetime


class InvoiceOut(ORM):
    id: UUID
    document_id: UUID
    seq: int
    source_kind: str
    location: dict
    invoice_number: str | None
    invoice_date: date | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: float | None
    tax: float | None
    total: float | None
    currency: str | None
    line_items: list[dict]
    fields: dict
    extraction_method: str | None
    model: str | None
    confidence: float | None
    status: str
    needs_review: bool
    reviewed_at: datetime | None
    updated_at: datetime | None


class InvoiceDetail(InvoiceOut):
    issues: list[IssueOut] = []
    corrections: list[CorrectionOut] = []
    document_filename: str | None = None
    document_file_type: str | None = None


class DocumentOut(ORM):
    id: UUID
    filename: str
    file_type: str | None
    size_bytes: int
    status: str
    progress: dict
    page_count: int | None
    text_method: str | None
    ocr_confidence: float | None
    invoice_count: int
    issue_count: int
    error_code: str | None
    error_message: str | None
    attempts: int
    duplicate_of: UUID | None
    created_at: datetime
    finished_at: datetime | None
    processing_ms: int | None
    batch_id: UUID | None


class PageOut(ORM):
    page_no: int
    label: str | None
    method: str
    ocr_confidence: float | None
    rotation: int | None
    deskew_angle: float | None
    chars: int = 0


class DocumentDetail(DocumentOut):
    sha256: str
    ai_calls: int
    pages: list[PageOut] = []
    invoices: list[InvoiceDetail] = []
    issues: list[IssueOut] = []          # document-level only
    events: list[EventOut] = []


class StatusOut(BaseModel):
    id: UUID
    status: str
    progress: dict
    invoice_count: int
    issue_count: int
    error_code: str | None
    processing_ms: int | None


class UploadResult(BaseModel):
    batch_id: UUID
    accepted: list[DocumentOut]
    rejected: list[dict] = Field(default_factory=list, description="Files refused before processing, with the reason")


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class CorrectionIn(BaseModel):
    fields: dict[str, Any] = Field(..., description="Field name -> corrected value. Use null to clear a value.",
                                   examples=[{"total": 1150.0, "invoice_date": "2026-03-14"}])
    reason: str | None = Field(None, max_length=500)
    corrected_by: str = Field("reviewer", max_length=120)


class SearchHit(BaseModel):
    invoice: InvoiceOut
    document_filename: str
    document_file_type: str | None
    score: float
    match: Literal["keyword", "semantic", "hybrid"]
    snippet: str | None = None


class SearchOut(BaseModel):
    query: str
    mode: str
    total: int
    took_ms: int
    hits: list[SearchHit]


class CrossCheckOut(BaseModel):
    id: int
    kind: str
    status: str
    differences: list[dict]
    created_at: datetime
    a: dict
    b: dict
