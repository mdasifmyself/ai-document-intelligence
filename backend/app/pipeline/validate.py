"""Validation rules. Plain code, no AI: maths must be exact and repeatable.

Every rule returns issues with a stable code, a severity and a plain-English message.
  error   -> the record needs review before it can be trusted
  warning -> worth a look; the record also goes to review
  info    -> context only (e.g. "confirmed by the Excel ledger")
"""
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, timedelta
from decimal import Decimal

from ..config import get_settings
from .types import ExtractedInvoice

REQUIRED = ("invoice_number", "invoice_date", "supplier_name", "total")
EXPECTED = ("customer_name", "subtotal", "tax", "currency")
LABELS = {"invoice_number": "invoice number", "invoice_date": "invoice date", "supplier_name": "supplier name",
          "customer_name": "customer name", "subtotal": "subtotal", "tax": "tax", "total": "total",
          "currency": "currency"}


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    field: str | None = None
    details: dict = dc_field(default_factory=dict)


def tolerance(amount: Decimal, lines: int = 0) -> Decimal:
    """Allowed rounding difference: 2 cents, plus half a cent per line item (per-line rounding)."""
    s = get_settings()
    base = Decimal(str(s.amount_tolerance_abs)) + Decimal(str(s.amount_tolerance_per_line)) * lines
    return max(base, abs(amount) * Decimal(str(s.amount_tolerance_rel)))


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def money(d: Decimal | None) -> str:
    return "—" if d is None else f"{d:,.2f}"


def validate(inv: ExtractedInvoice, today: date | None = None) -> list[Issue]:
    today = today or date.today()
    issues: list[Issue] = []
    is_record = inv.source_kind == "record"

    # 1. Not an invoice at all
    if inv.document_kind == "other" and not any(inv.get(f) for f in ("invoice_number", "total")):
        issues.append(Issue("NOT_AN_INVOICE", "warning", "This page does not look like an invoice or receipt."))

    # 2. Missing fields (spreadsheet rows only need the columns the sheet has)
    for name in REQUIRED:
        if is_record and name not in inv.fields:
            continue
        if inv.get(name) is None:
            f = inv.fields.get(name)
            if f is not None and f.verified is False:
                continue  # reported below as unverified, not as missing
            if name == "invoice_date" and f is not None and f.raw:
                continue  # reported below as ambiguous
            issues.append(Issue("MISSING_FIELD", "error", f"The {LABELS[name]} is missing.", name))
    if not is_record:
        for name in EXPECTED:
            if inv.get(name) is None and not (inv.fields.get(name) and inv.fields[name].verified is False):
                issues.append(Issue("MISSING_FIELD", "warning", f"The {LABELS[name]} was not found.", name))

    # 3. Values the AI suggested but could not prove from the document
    for name, f in inv.fields.items():
        if f.verified is False:
            issues.append(Issue("UNVERIFIED_VALUE", "warning",
                                f"The {LABELS.get(name, name)} could not be confirmed in the document, so it was left empty.",
                                name, {"suggested_evidence": f.evidence}))

    from_image = [LABELS.get(n, n) for n, f in inv.fields.items()
                  if f.source == "vision" and f.value is not None and f.verified is None]
    if from_image:
        issues.append(Issue("READ_FROM_IMAGE", "warning",
                            "The scan is hard to read, so these values were read from the page image: "
                            f"{', '.join(from_image)}. Please confirm them.", None, {"fields": from_image}))
    for w in inv.warnings:
        if w.startswith("disagree:"):
            _, name, rest = w.split(":", 2)
            tv, vv, chosen = (rest.split("|") + ["", "", ""])[:3]
            issues.append(Issue("READINGS_DISAGREE", "warning",
                                f"Two independent readings of the {LABELS.get(name, name)} differ: the OCR text says "
                                f"“{tv}”, the page image says “{vv}”. “{chosen}” was kept; please check the page.",
                                name, {"ocr_text": tv, "image": vv, "kept": chosen}))
    if "self_check_reread" in inv.warnings:
        issues.append(Issue("SELF_CHECK_REREAD", "info",
                            "The first reading of this scan had missing or inconsistent values, so the page image was "
                            "read again; the second reading passed more checks and was kept."))

    # 4. Numbers that cannot be right
    subtotal, tax, total = (_dec(inv.get(n)) for n in ("subtotal", "tax", "total"))
    for name, v in (("subtotal", subtotal), ("tax", tax), ("total", total)):
        if v is not None and v < 0 and inv.document_kind != "credit_note":
            issues.append(Issue("INVALID_AMOUNT", "error", f"The {name} is negative ({money(v)}).", name))
        if v is not None and abs(v) >= Decimal("1e11"):
            issues.append(Issue("INVALID_AMOUNT", "error", f"The {name} is unrealistically large ({money(v)}).", name))

    # 5. Subtotal + tax = total
    if subtotal is not None and total is not None:
        expected = subtotal + (tax or Decimal(0))
        if abs(expected - total) > tolerance(total, len(inv.line_items or [])):
            issues.append(Issue("TOTAL_MISMATCH", "error",
                                f"Subtotal {money(subtotal)} + tax {money(tax or Decimal(0))} = {money(expected)}, "
                                f"but the total says {money(total)}.", "total",
                                {"expected": float(expected), "printed": float(total), "difference": float(total - expected)}))
    if tax is not None and subtotal and subtotal > 0 and tax / subtotal > Decimal("0.35"):
        issues.append(Issue("UNUSUAL_TAX_RATE", "warning",
                            f"Tax is {tax / subtotal:.0%} of the subtotal, which is unusually high.", "tax"))

    # 6. Line items
    items = inv.line_items or []
    amounts = [_dec(i.get("amount")) for i in items]
    for idx, it in enumerate(items, start=1):
        q, p, a = _dec(it.get("quantity")), _dec(it.get("unit_price")), _dec(it.get("amount"))
        if q is not None and p is not None and a is not None and abs(q * p - a) > tolerance(a):
            issues.append(Issue("LINE_ITEM_MATH", "error",
                                f"Line {idx} ({it.get('description', '')[:40]}): {q:g} × {money(p)} = {money(q * p)}, "
                                f"but the line says {money(a)}.", "line_items", {"line": idx}))
    if items and all(a is not None for a in amounts):
        items_sum = sum(amounts, Decimal(0))
        target, label = (subtotal, "subtotal") if subtotal is not None else (
            (total, "total") if total is not None and not tax else (None, None))
        if target is not None and abs(items_sum - target) > tolerance(target, len(items)):
            issues.append(Issue("LINE_ITEMS_MISMATCH", "error",
                                f"The line items add up to {money(items_sum)}, but the {label} says {money(target)}.",
                                label, {"items_sum": float(items_sum), "printed": float(target)}))

    # 7. Dates
    d = inv.get("invoice_date")
    if isinstance(d, date):
        if d > today + timedelta(days=2):
            issues.append(Issue("FUTURE_DATE", "warning", f"The invoice date {d.isoformat()} is in the future.", "invoice_date"))
        if d.year < 2000:
            issues.append(Issue("INVALID_DATE", "error", f"The invoice date {d.isoformat()} looks wrong.", "invoice_date"))
    f = inv.fields.get("invoice_date")
    if f is not None and f.value is None and f.raw:
        issues.append(Issue("AMBIGUOUS_DATE", "warning",
                            f"The date \"{f.raw}\" can be read as day/month or month/day. Please confirm it.",
                            "invoice_date", {"raw": f.raw}))

    # 8. Low reading quality
    if inv.ocr_confidence is not None and inv.ocr_confidence < get_settings().ocr_low_confidence and inv.method != "llm_vision":
        issues.append(Issue("LOW_OCR_QUALITY", "warning",
                            f"The scan is hard to read (OCR confidence {inv.ocr_confidence:.0f}%). Check the values.", None))
    return issues


def needs_review(issues) -> bool:
    return any(i.severity in ("error", "warning") for i in issues)
