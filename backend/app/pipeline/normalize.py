"""Turn printed values into clean data: amounts, dates, currencies, names, invoice numbers."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from dateutil import parser as dateparser

CURRENCY_SYMBOLS = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "৳": "BDT", "TK": "BDT", "TK.": "BDT",
                    "TAKA": "BDT", "₹": "INR", "RS": "INR", "RS.": "INR", "¥": "JPY", "A$": "AUD", "C$": "CAD"}
ISO_CURRENCIES = {"USD", "EUR", "GBP", "BDT", "INR", "JPY", "AUD", "CAD", "CHF", "CNY", "SGD", "AED", "SAR",
                  "MYR", "NZD", "SEK", "NOK", "DKK", "PKR", "LKR", "NPR", "THB", "HKD", "ZAR"}
COMPANY_SUFFIXES = r"\b(ltd|limited|llc|l\.l\.c|inc|incorporated|co|company|corp|corporation|plc|pvt|private|gmbh|sa|bv|llp)\b\.?"


def parse_amount(value) -> Decimal | None:
    """'1,234.50' / '1.234,50' / '(45.00)' / '$ 99' / 99.5  ->  Decimal. None if not a number."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            return None
        return d if d.is_finite() else None
    s = str(value).strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.endswith("-")
    s = re.sub(r"[^\d,.\s]", "", s).strip().replace(" ", "")
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # 1.234,56
        else:
            s = s.replace(",", "")                     # 1,234.56
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 2 and len(parts) >= 2:
            s = "".join(parts[:-1]) + "." + parts[-1]  # 1234,56
        else:
            s = s.replace(",", "")                     # 1,234 or 12,34,567 (South Asian grouping)
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) == 2 else s.replace(".", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if negative else d


def numbers_in(text: str) -> list[Decimal]:
    """All amounts that appear in a snippet of text."""
    out = []
    for m in re.finditer(r"\(?-?\d[\d.,]*\d\)?|\d", text or ""):
        d = parse_amount(m.group(0).strip())
        if d is not None:
            out.append(d)
    return out


def parse_date(value, dayfirst_hint: bool | None = None) -> tuple[date | None, bool]:
    """Returns (date, ambiguous). '03/04/2026' is ambiguous; '2026-04-03' and '14/03/2026' are not."""
    if value is None or value == "":
        return None, False
    if isinstance(value, datetime):
        return value.date(), False
    if isinstance(value, date):
        return value, False
    s = str(value).strip()
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), False
        except ValueError:
            return None, False
    numeric = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", s)
    ambiguous = False
    if numeric:
        a, b = int(numeric.group(1)), int(numeric.group(2))
        if a <= 12 and b <= 12 and a != b:
            ambiguous = True
        dayfirst = a > 12 if not ambiguous else bool(dayfirst_hint)
    else:
        dayfirst = bool(dayfirst_hint)
    try:
        d = dateparser.parse(s, dayfirst=dayfirst, fuzzy=False, default=datetime(1900, 1, 1))
    except (ValueError, OverflowError, TypeError):
        return None, False
    if d.year == 1900:
        return None, False
    return d.date(), ambiguous


def normalize_currency(value) -> str | None:
    if not value:
        return None
    s = str(value).strip().upper()
    if s in ISO_CURRENCIES:
        return s
    if s in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[s]
    for sym, code in CURRENCY_SYMBOLS.items():
        if s.startswith(sym):
            return code
    m = re.search(r"\b([A-Z]{3})\b", s)
    if m and m.group(1) in ISO_CURRENCIES:
        return m.group(1)
    return None


def normalize_name(value) -> str | None:
    """'Northwind Medical Supplies Ltd.' -> 'northwind medical supplies' (for matching only)."""
    if not value:
        return None
    s = str(value).lower()
    s = re.sub(COMPANY_SUFFIXES, " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def normalize_invoice_number(value) -> str | None:
    """'inv # 00-2041 ' -> 'INV002041' (for matching only; the printed value is kept as is)."""
    if not value:
        return None
    s = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return s or None


def normalize_text(value: str) -> str:
    """Lowercase, unify quotes and dashes, collapse spaces: used to compare evidence with page text."""
    s = (value or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def to_float(d: Decimal | None) -> float | None:
    return float(d) if d is not None else None
