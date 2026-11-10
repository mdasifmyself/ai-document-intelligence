"""Read XLSX, XLS and CSV files.

Every sheet is read. When a sheet has recognisable column headers (Invoice No, Date, Supplier, Total…),
its rows become invoice records directly: exact, fast and with no AI needed. Line-item sheets are joined
to their invoices by invoice number. Sheets laid out like a printed invoice (labels in cells, not a table)
are passed to the AI extractor as text.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from charset_normalizer import from_bytes
from openpyxl.utils import get_column_letter
from rapidfuzz import fuzz

from .detect import ProcessingError
from .normalize import normalize_currency, parse_amount, parse_date
from .readers import Page
from .types import CORE_FIELDS, ExtractedInvoice, FieldValue

SYNONYMS = {
    "invoice_number": ["invoice number", "invoice no", "invoice #", "invoice num", "invoice id", "inv no", "inv #",
                       "inv number", "invoice", "bill no", "bill number", "document number", "doc no", "ref no"],
    "invoice_date": ["invoice date", "date", "bill date", "issue date", "issued", "document date", "inv date"],
    "supplier_name": ["supplier", "supplier name", "vendor", "vendor name", "seller", "issuer", "company", "from"],
    "customer_name": ["customer", "customer name", "client", "client name", "buyer", "bill to", "billed to"],
    "subtotal": ["subtotal", "sub total", "sub-total", "net", "net amount", "amount before tax", "taxable amount"],
    "tax": ["tax", "vat", "gst", "tax amount", "vat amount", "sales tax", "tax total"],
    "total": ["total", "grand total", "total amount", "amount due", "gross amount", "invoice total", "total due",
              "gross", "invoice amount"],
    "currency": ["currency", "curr", "ccy", "currency code"],
    "description": ["description", "item", "item description", "product", "service", "details", "particulars"],
    "quantity": ["qty", "quantity", "units", "qnty"],
    "unit_price": ["unit price", "price", "rate", "unit cost", "price per unit"],
    "amount": ["amount", "line total", "line amount", "value", "line value", "ext price", "extended price"],
}
MAX_TEXT_ROWS = 400


@dataclass
class SpreadsheetResult:
    pages: list[Page]
    records: list[ExtractedInvoice] = field(default_factory=list)
    layout_sheets: list[tuple[int, str, str]] = field(default_factory=list)  # (sheet_no, name, text) for the AI


def _norm_header(h) -> str:
    s = str(h or "").strip().lower()
    s = re.sub(r"[^a-z0-9# ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def match_header(h) -> str | None:
    s = _norm_header(h)
    if not s or ("due" in s and "date" in s):
        return None
    for key, words in SYNONYMS.items():
        if s in words:
            return key
    best, best_score = None, 0.0
    for key, words in SYNONYMS.items():
        for w in words:
            score = fuzz.ratio(s, w)
            if score > best_score:
                best, best_score = key, score
    return best if best_score >= 90 else None


def _cell_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    return str(v).strip()


def _find_header(df: pd.DataFrame) -> tuple[int | None, dict[int, str]]:
    best_row, best_map = None, {}
    for r in range(min(15, len(df))):
        mapping = {}
        for c, v in enumerate(df.iloc[r].tolist()):
            key = match_header(v)
            if key and key not in mapping.values():
                mapping[c] = key
        if len(mapping) > len(best_map):
            best_row, best_map = r, mapping
    return (best_row, best_map) if len(best_map) >= 2 else (None, {})


def _sheet_text(df: pd.DataFrame) -> str:
    lines = []
    for r in range(min(len(df), MAX_TEXT_ROWS)):
        cells = [_cell_str(v) for v in df.iloc[r].tolist()]
        if any(cells):
            lines.append(" | ".join(cells).rstrip(" |"))
    return "\n".join(lines)


def _field(value, sheet: str, row: int, col: int, raw) -> FieldValue:
    ref = f"{sheet}!{get_column_letter(col + 1)}{row + 1}"
    return FieldValue(value=value, evidence=f"{ref}: {_cell_str(raw)}", raw=_cell_str(raw), verified=True,
                      confidence=0.98, source="cell")


def _register_rows(df, header_row, cmap, sheet) -> list[ExtractedInvoice]:
    out = []
    inv_cols = {v: k for k, v in cmap.items()}
    if "total" not in inv_cols and "amount" in inv_cols:
        inv_cols["total"] = inv_cols.pop("amount")
    for r in range(header_row + 1, len(df)):
        row = df.iloc[r].tolist()
        cells = {k: row[c] if c < len(row) else None for k, c in inv_cols.items()}
        if not any(_cell_str(v) for v in cells.values()):
            continue
        first = next((_cell_str(v) for v in row if _cell_str(v)), "")
        has_identity = any(_cell_str(cells.get(k)) for k in ("invoice_number", "supplier_name", "invoice_date"))
        if not has_identity or (not _cell_str(cells.get("invoice_number")) and re.search(r"\btotals?\b", first, re.I)):
            continue  # summary row such as "TOTAL" or a row with amounts only
        fields: dict[str, FieldValue] = {}
        for key, c in inv_cols.items():
            if key not in CORE_FIELDS:
                continue
            raw = row[c] if c < len(row) else None
            if not _cell_str(raw):
                fields[key] = FieldValue(None)
                continue
            if key in ("subtotal", "tax", "total"):
                val = parse_amount(raw)
            elif key == "invoice_date":
                val, _amb = parse_date(raw)
            elif key == "currency":
                val = normalize_currency(raw)
            else:
                val = _cell_str(raw)
            fields[key] = _field(val, sheet, r, c, raw)
        if "currency" not in fields:
            sym = next((normalize_currency(m) for v in row for m in re.findall(r"[$€£৳]|\b[A-Z]{3}\b", _cell_str(v))
                        if normalize_currency(m)), None)
            fields["currency"] = FieldValue(sym, evidence=f"{sheet} row {r + 1}" if sym else None,
                                            verified=True if sym else None, confidence=0.9 if sym else 0, source="cell")
        out.append(ExtractedInvoice(fields=fields, method="spreadsheet_columns", source_kind="record",
                                    location={"sheet": sheet, "row": r + 1}))
    return out


def _line_item_rows(df, header_row, cmap, sheet) -> dict[str, list[dict]]:
    items: dict[str, list[dict]] = {}
    cols = {v: k for k, v in cmap.items()}
    for r in range(header_row + 1, len(df)):
        row = df.iloc[r].tolist()
        get = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else None
        num = _cell_str(get("invoice_number"))
        desc = _cell_str(get("description"))
        if not num or not desc:
            continue
        items.setdefault(num, []).append({
            "description": desc,
            "quantity": float(q) if (q := parse_amount(get("quantity"))) is not None else None,
            "unit_price": float(p) if (p := parse_amount(get("unit_price"))) is not None else None,
            "amount": float(a) if (a := parse_amount(get("amount"))) is not None else None,
            "evidence": f"{sheet}!row {r + 1}",
        })
    return items


def _load_frames(path: Path, file_type: str) -> dict[str, pd.DataFrame]:
    try:
        if file_type == "csv":
            raw = path.read_bytes()
            best = from_bytes(raw).best()
            text = str(best) if best else raw.decode("utf-8", errors="replace")
            sample = text[:4096]
            try:
                delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delim = ","
            df = pd.read_csv(io.StringIO(text), sep=delim, header=None, dtype=str, keep_default_na=False,
                             engine="python", on_bad_lines="skip")
            return {path.stem: df}
        engine = "xlrd" if file_type == "xls" else "openpyxl"
        return pd.read_excel(path, sheet_name=None, header=None, dtype=object, engine=engine)
    except ProcessingError:
        raise
    except Exception as e:
        raise ProcessingError("CORRUPTED_FILE", f"The spreadsheet could not be read ({type(e).__name__}).")


def read_spreadsheet(path: Path, file_type: str) -> SpreadsheetResult:
    frames = _load_frames(path, file_type)
    if not frames:
        raise ProcessingError("EMPTY_DOCUMENT", "The spreadsheet has no sheets.")
    result = SpreadsheetResult(pages=[])
    all_items: dict[str, list[dict]] = {}
    for i, (name, df) in enumerate(frames.items(), start=1):
        df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        df.columns = range(df.shape[1])
        text = _sheet_text(df)
        result.pages.append(Page(page_no=i, text=text, method="spreadsheet", label=str(name)))
        if df.empty:
            continue
        header_row, cmap = _find_header(df)
        keys = set(cmap.values())
        if header_row is not None and "invoice_number" in keys and "description" in keys:
            for num, items in _line_item_rows(df, header_row, cmap, str(name)).items():
                all_items.setdefault(num, []).extend(items)
        elif header_row is not None and ("total" in keys or "amount" in keys) and \
                ({"invoice_number", "supplier_name"} & keys) and len(keys & set(CORE_FIELDS) | (keys & {"amount"})) >= 3:
            result.records.extend(_register_rows(df, header_row, cmap, str(name)))
        elif re.search(r"invoice|bill|total", text, re.I):
            result.layout_sheets.append((i, str(name), text))
    for rec in result.records:
        num = rec.get("invoice_number")
        if num and num in all_items:
            rec.line_items = all_items.pop(num)
    if not result.records and not result.layout_sheets and all_items:
        # only line items were found: keep them as records so nothing is lost
        for num, items in all_items.items():
            result.records.append(ExtractedInvoice(
                fields={"invoice_number": FieldValue(num, evidence=items[0]["evidence"], verified=True,
                                                     confidence=0.98, source="cell")},
                line_items=items, method="spreadsheet_columns", source_kind="record",
                location={"sheet": items[0]["evidence"].split("!")[0]}))
    return result
