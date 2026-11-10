"""Database tables.

documents ─┬─< document_pages        (text of every page or sheet, how it was read, OCR confidence)
           ├─< invoices ─┬─< validation_issues
           │             ├─< corrections        (manual edits: old value, new value, who, when, why)
           │             └─< cross_checks       (same invoice found in two documents)
           ├─< validation_issues     (document-level problems, e.g. corrupted file)
           └─< processing_events     (processing history: every stage, duration, errors)
"""
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (Boolean, Computed, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import get_settings
from .db import Base

EMBED_DIM = get_settings().embedding_dim

DOC_STATUSES = ("queued", "processing", "completed", "needs_review", "failed")
INVOICE_STATUSES = ("ok", "needs_review", "reviewed")


def _uuid():
    return uuid.uuid4()


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str | None] = mapped_column(String(16))        # pdf, image, xlsx, xls, csv
    mime: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[dict] = mapped_column(JSONB, default=dict)      # {"stage": "ocr", "done": 3, "total": 10}
    page_count: Mapped[int | None] = mapped_column(Integer)
    text_method: Mapped[str | None] = mapped_column(String(20))      # digital, ocr, mixed, vision, spreadsheet
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    invoice_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ai_calls: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # last sign of life from the worker
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)

    full_text: Mapped[str | None] = mapped_column(Text, deferred=True)       # loaded only when asked for
    text_tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', coalesce(filename,'') || ' ' || "
                                                "left(coalesce(full_text,''), 400000))", persisted=True))

    pages: Mapped[list["DocumentPage"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                       order_by="DocumentPage.page_no")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                     order_by="Invoice.seq")
    issues: Mapped[list["ValidationIssue"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    events: Mapped[list["ProcessingEvent"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                           order_by="ProcessingEvent.id")

    __table_args__ = (Index("ix_documents_text_tsv", "text_tsv", postgresql_using="gin"),)


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_no: Mapped[int] = mapped_column(Integer)                    # 1-based; for spreadsheets = sheet number
    label: Mapped[str | None] = mapped_column(String(120))           # sheet name for spreadsheets
    method: Mapped[str] = mapped_column(String(20))                  # digital, ocr, vision, spreadsheet
    text: Mapped[str] = mapped_column(Text, default="")
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    rotation: Mapped[int | None] = mapped_column(Integer)
    deskew_angle: Mapped[float | None] = mapped_column(Float)

    document: Mapped[Document] = relationship(back_populates="pages")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1)             # order inside the document
    source_kind: Mapped[str] = mapped_column(String(12), default="document")  # document | record (spreadsheet row)
    location: Mapped[dict] = mapped_column(JSONB, default=dict)      # pages or sheet/rows where it was found

    invoice_number: Mapped[str | None] = mapped_column(String(100))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    customer_name: Mapped[str | None] = mapped_column(String(255))
    subtotal: Mapped[float | None] = mapped_column(Numeric(16, 2))
    tax: Mapped[float | None] = mapped_column(Numeric(16, 2))
    total: Mapped[float | None] = mapped_column(Numeric(16, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    line_items: Mapped[list] = mapped_column(JSONB, default=list)

    fields: Mapped[dict] = mapped_column(JSONB, default=dict)        # per field: value, evidence, verified, confidence, source
    extraction_method: Mapped[str | None] = mapped_column(String(30))  # llm_text, llm_vision, spreadsheet_columns
    model: Mapped[str | None] = mapped_column(String(60))
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="ok", index=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_ai_output: Mapped[dict | None] = mapped_column(JSONB, deferred=True)

    invoice_number_norm: Mapped[str | None] = mapped_column(String(100), index=True)
    supplier_norm: Mapped[str | None] = mapped_column(String(255), index=True)
    search_text: Mapped[str | None] = mapped_column(Text)
    search_tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', coalesce(search_text,''))", persisted=True))
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True, deferred=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    document: Mapped[Document] = relationship(back_populates="invoices")
    issues: Mapped[list["ValidationIssue"]] = relationship(back_populates="invoice", cascade="all, delete-orphan",
                                                           overlaps="issues")
    corrections: Mapped[list["Correction"]] = relationship(back_populates="invoice", cascade="all, delete-orphan",
                                                           order_by="Correction.id")

    __table_args__ = (
        Index("ix_invoices_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_invoices_supplier_trgm", "supplier_name", postgresql_using="gin",
              postgresql_ops={"supplier_name": "gin_trgm_ops"}),
        Index("ix_invoices_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )


class ValidationIssue(Base):
    __tablename__ = "validation_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(10))                # error, warning, info
    field: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="issues", overlaps="issues")
    invoice: Mapped[Invoice | None] = relationship(back_populates="issues", overlaps="issues")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(40))
    old_value: Mapped[dict | list | str | float | None] = mapped_column(JSONB)
    new_value: Mapped[dict | list | str | float | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    corrected_by: Mapped[str] = mapped_column(String(120), default="reviewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="corrections")


class CrossCheck(Base):
    __tablename__ = "cross_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_a: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    invoice_b: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))                    # pdf_pdf, pdf_excel, image_excel, ...
    status: Mapped[str] = mapped_column(String(12))                  # match, mismatch, duplicate
    differences: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("invoice_a", "invoice_b", name="uq_cross_check_pair"),)


class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(12))                  # started, completed, failed, info
    message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="events")
