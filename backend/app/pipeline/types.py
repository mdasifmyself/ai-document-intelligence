"""Shared result types for the pipeline."""
from dataclasses import dataclass, field
from typing import Any

CORE_FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name",
               "subtotal", "tax", "total", "currency")
AMOUNT_FIELDS = ("subtotal", "tax", "total")


@dataclass
class FieldValue:
    value: Any = None
    evidence: str | None = None      # the exact text (or cell) the value came from
    raw: str | None = None           # value as printed, before cleaning (dates)
    verified: bool | None = None     # True = evidence found in the document; None = not checkable (vision)
    confidence: float = 0.0          # 0-1, see pipeline/confidence notes in docs
    source: str = "text"             # text | vision | vision+text | cell | manual
    suggested: object = None         # what the AI proposed when the value could not be proven (shown to reviewers)

    def as_dict(self) -> dict:
        v = self.value
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        elif v is not None and type(v).__name__ == "Decimal":
            v = float(v)
        sug = self.suggested
        if sug is not None and type(sug).__name__ == "Decimal":
            sug = float(sug)
        elif hasattr(sug, "isoformat"):
            sug = sug.isoformat()
        out = {"value": v, "evidence": self.evidence, "raw": self.raw, "verified": self.verified,
               "confidence": round(self.confidence, 3), "source": self.source}
        if sug is not None:
            out["suggested"] = sug
        return out


@dataclass
class ExtractedInvoice:
    fields: dict[str, FieldValue]
    line_items: list[dict] = field(default_factory=list)
    method: str = "llm_text"                     # llm_text | llm_vision | spreadsheet_columns
    model: str | None = None
    location: dict = field(default_factory=dict)  # {"pages": [1, 2]} or {"sheet": "Invoices", "row": 5}
    source_kind: str = "document"                # document | record
    document_kind: str = "invoice"               # invoice | receipt | credit_note | other
    notes: str | None = None
    raw: dict | None = None
    ocr_confidence: float | None = None
    warnings: list[str] = field(default_factory=list)

    def get(self, name: str):
        f = self.fields.get(name)
        return f.value if f else None
