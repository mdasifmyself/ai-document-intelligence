"""Split a long PDF or TIFF into separate invoices.

A 1,000-page batch usually holds hundreds of invoices, some one page, some several. A new invoice
starts when a page shows a different invoice number than the previous page and is not marked as a
continuation ("Page 2 of 3", "continued"). Pages with no number stay with the invoice before them.
"""
import re
from dataclasses import dataclass, field

from .readers import Page

INVOICE_NO = re.compile(
    r"(?i)\b(?:invoice|inv|bill|tax\s+invoice)\s*(?:no\.?|number|num\.?|#|id)?\s*[:#.\-]?\s*"
    r"(?=[A-Z0-9\-/]*\d)([A-Z0-9][A-Z0-9\-/]{2,24})")
CONTINUED = re.compile(r"(?i)\bpage\s*([2-9]|\d{2,})\s*(?:of|/)\s*\d+|\bcontinued\b|\bcont'?d\b")
FIRST_PAGE = re.compile(r"(?i)\bpage\s*1\s*(?:of|/)\s*\d+")


@dataclass
class Segment:
    pages: list[Page] = field(default_factory=list)
    invoice_number: str | None = None

    @property
    def page_numbers(self) -> list[int]:
        return [p.page_no for p in self.pages]

    @property
    def text(self) -> str:
        return "\n\n".join(f"--- page {p.page_no} ---\n{p.text}" for p in self.pages)


def find_invoice_number(text: str) -> str | None:
    head = text[: max(600, len(text) // 2)]
    for m in INVOICE_NO.finditer(head):
        token = m.group(1).strip("-/.")
        if len(token) >= 3 and not re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", token):
            return token
    return None


def split_invoices(pages: list[Page]) -> list[Segment]:
    if len(pages) <= 1:
        return [Segment(pages=list(pages), invoice_number=find_invoice_number(pages[0].text) if pages else None)]
    segments: list[Segment] = []
    current: Segment | None = None
    for page in pages:
        number = find_invoice_number(page.text or "")
        continued = bool(CONTINUED.search(page.text or ""))
        starts_new = (
            current is None
            or (number and current.invoice_number and number != current.invoice_number and not continued)
            or (FIRST_PAGE.search(page.text or "") and current.pages)
            or (number and not current.invoice_number and not continued and current.pages
                and any(p.text.strip() for p in current.pages) and _looks_complete(current))
        )
        if starts_new:
            current = Segment(invoice_number=number)
            segments.append(current)
        current.pages.append(page)
        if number and not current.invoice_number:
            current.invoice_number = number
    return segments


def _looks_complete(seg: Segment) -> bool:
    """The previous pages already contain a total, so a new numbered page is a new invoice."""
    return bool(re.search(r"(?i)\b(grand\s+total|total\s+due|amount\s+due|total)\b", seg.pages[-1].text or ""))
