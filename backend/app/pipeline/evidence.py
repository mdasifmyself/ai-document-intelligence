"""The "no made-up values" guard.

The model must quote where each value came from. We then check, in code, that
  1) the quote really appears in the document text (exactly, or nearly for OCR text), and
  2) the value really appears inside the quote.
If either check fails, the value is removed (set to null) and the invoice is flagged for review.
"""
import re
from decimal import Decimal

from rapidfuzz import fuzz

from .normalize import normalize_currency, normalize_text, numbers_in, parse_amount

EXACT = 1.0
OCR_FUZZY_MIN = 88        # OCR text can differ by a few characters from what the model "corrected"


def quote_in_text(evidence: str | None, doc_text_norm: str) -> float:
    """0 = not found, 1 = exact; values between = fuzzy match strength."""
    if not evidence:
        return 0.0
    ev = normalize_text(evidence)
    if len(ev) < 2:
        return 0.0
    if ev in doc_text_norm:
        return EXACT
    score = fuzz.partial_ratio(ev, doc_text_norm, score_cutoff=OCR_FUZZY_MIN)
    return score / 100 if score else 0.0


def value_in_quote(value, evidence: str, kind: str) -> bool:
    if value is None or not evidence:
        return False
    if kind == "amount":
        v = parse_amount(value)
        return v is not None and any(abs(n - v) <= Decimal("0.005") for n in numbers_in(evidence))
    if kind == "date":
        return True  # dates are checked through their printed `raw` form instead
    if kind == "currency":
        tokens = re.findall(r"US\$|A\$|C\$|[$€£৳₹¥]|\bTk\.?|\b[A-Za-z]{3}\b", evidence)
        return any(normalize_currency(t) == value for t in tokens)
    return fuzz.partial_ratio(normalize_text(str(value)), normalize_text(evidence)) >= 85


def check(value, evidence: str | None, doc_text_norm: str, kind: str) -> tuple[bool, float]:
    """Returns (verified, match_strength)."""
    strength = quote_in_text(evidence, doc_text_norm)
    if strength == 0:
        return False, 0.0
    if not value_in_quote(value, evidence, kind):
        return False, strength
    return True, strength
