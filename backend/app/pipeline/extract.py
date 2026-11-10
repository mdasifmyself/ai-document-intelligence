"""AI extraction of invoice fields, followed by the evidence check and value cleaning."""
import base64
import io
from typing import Callable

from PIL import Image

from ..ai import client
from ..ai.prompts import EXTRACTION_SCHEMA, EXTRACTION_SYSTEM, VISION_HINT
from ..config import get_settings
from . import evidence
from .normalize import normalize_currency, normalize_text, parse_amount, parse_date
from .segment import Segment
from .types import AMOUNT_FIELDS, ExtractedInvoice, FieldValue

MAX_CHARS = 24000
STRING_FIELDS = ("invoice_number", "supplier_name", "customer_name")


def _clip(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    return text[:16000] + "\n[... middle of the document omitted ...]\n" + text[-8000:]


def _jpeg_data_url(img: Image.Image) -> str:
    img = img.convert("RGB")
    img.thumbnail((1700, 1700))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _page_confidence(seg: Segment) -> float | None:
    confs = [p.ocr_confidence for p in seg.pages if p.method == "ocr" and p.ocr_confidence is not None]
    return round(sum(confs) / len(confs), 1) if confs else None


def needs_vision(seg: Segment) -> bool:
    s = get_settings()
    if not s.vision_fallback:
        return False
    ocr_pages = [p for p in seg.pages if p.method == "ocr"]
    if not ocr_pages or len(ocr_pages) != len(seg.pages):
        return False
    conf = _page_confidence(seg) or 0
    chars = sum(len(p.text.strip()) for p in seg.pages)
    return conf < s.ocr_low_confidence or chars < 80


def _cache_key(model: str, text: str, images: list[Image.Image] | None) -> str:
    import hashlib
    from ..ai.prompts import PROMPT_VERSION
    h = hashlib.sha256(f"{PROMPT_VERSION}|{model}|".encode() + text.encode())
    for im in images or []:
        h.update(im.tobytes())
    return "docintel:ai_cache:" + h.hexdigest()


def _cache_get(key: str):
    s = get_settings()
    if not s.ai_cache or s.ai_provider == "fake":
        return None
    try:
        import json
        from redis import Redis
        v = Redis.from_url(s.redis_url, socket_timeout=1).get(key)
        return json.loads(v) if v else None
    except Exception:
        return None


def _cache_put(key: str, data: dict):
    s = get_settings()
    if not s.ai_cache or s.ai_provider == "fake":
        return
    try:
        import json
        from redis import Redis
        Redis.from_url(s.redis_url, socket_timeout=1).set(key, json.dumps(data), ex=7 * 86400)
    except Exception:
        pass


def ask_model(text: str, images: list[Image.Image] | None = None) -> tuple[dict, str]:
    """Same document text (and images) + same prompt version + same model = the saved answer is reused.
    This makes long jobs resumable after a restart and reprocessing free of repeated AI cost."""
    s = get_settings()
    model = s.vision_model if images else s.extraction_model
    key = _cache_key(model, text, images)
    cached = _cache_get(key)
    if cached is not None:
        return cached, model
    data, model = _ask_model_uncached(text, images)
    _cache_put(key, data)
    return data, model


def _ask_model_uncached(text: str, images: list[Image.Image] | None = None) -> tuple[dict, str]:
    s = get_settings()
    if images:
        # image only: the OCR text is not shown, so the image reading cannot copy an OCR mistake
        content = [{"type": "input_text", "text": VISION_HINT}]
        content += [{"type": "input_image", "image_url": _jpeg_data_url(im)} for im in images[:3]]
        return client.structured(s.vision_model, EXTRACTION_SYSTEM, content, EXTRACTION_SCHEMA, "invoice"), s.vision_model
    return client.structured(s.extraction_model, EXTRACTION_SYSTEM, _clip(text), EXTRACTION_SCHEMA, "invoice"), \
        s.extraction_model


def _confidence(verified: bool | None, strength: float, method_ocr: bool, ocr_conf: float | None, vision: bool) -> float:
    if vision and verified is None:
        return 0.6
    if not verified:
        return 0.0
    c = 0.97 if strength >= 1.0 else 0.8 * strength
    if method_ocr and ocr_conf is not None:
        c *= max(0.55, min(1.0, ocr_conf / 90))
    return c


def build_invoice(data: dict, doc_text: str, *, method: str, model: str, location: dict,
                  ocr_conf: float | None, any_ocr: bool) -> ExtractedInvoice:
    """Turn the model's JSON into checked, cleaned fields. Unproven values become null."""
    vision = method == "llm_vision"
    text_norm = normalize_text(doc_text)
    fields: dict[str, FieldValue] = {}
    warnings: list[str] = []

    def finish(name, value, ev, raw=None, kind="string"):
        if value is None:
            fields[name] = FieldValue(None, raw=raw)
            return
        ok, strength = evidence.check(raw if kind == "date" else value, ev, text_norm, kind)
        if kind == "date" and ok:
            ok = evidence.value_in_quote(raw, ev, "string") if raw else False
        if not ok and not vision:
            fields[name] = FieldValue(None, evidence=ev, raw=raw, verified=False, source="text", suggested=value)
            warnings.append(name)
            return
        verified = True if ok else None
        fields[name] = FieldValue(value, evidence=ev, raw=raw, verified=verified,
                                  confidence=_confidence(verified, strength, any_ocr, ocr_conf, vision),
                                  source="vision" if vision and not ok else "text")

    for name in STRING_FIELDS:
        f = data.get(name) or {}
        v = f.get("value")
        finish(name, v.strip() if isinstance(v, str) and v.strip() else None, f.get("evidence"))

    for name in AMOUNT_FIELDS:
        f = data.get(name) or {}
        v = parse_amount(f.get("value"))
        finish(name, v, f.get("evidence"), kind="amount")

    cur = data.get("currency") or {}
    finish("currency", normalize_currency(cur.get("value")), cur.get("evidence"), kind="currency")

    d = data.get("invoice_date") or {}
    raw = d.get("raw")
    parsed, ambiguous = parse_date(d.get("value")) if d.get("value") else (None, False)
    if raw:
        from_raw, amb_raw = parse_date(raw)
        if from_raw and not amb_raw:
            parsed = from_raw           # the printed form wins over the model's reading
        if amb_raw:
            parsed, ambiguous = None, True   # 03/04/2026 could be March or April: never pick one silently
    finish("invoice_date", parsed, d.get("evidence"), raw=raw, kind="date")
    if ambiguous and fields["invoice_date"].value is None and raw:
        fields["invoice_date"].raw = raw
        fields["invoice_date"].evidence = d.get("evidence")

    items = []
    for it in data.get("line_items") or []:
        amount = parse_amount(it.get("amount"))
        ok_item = vision or evidence.quote_in_text(it.get("evidence"), text_norm) > 0 or \
            evidence.quote_in_text(it.get("description"), text_norm) > 0
        items.append({
            "description": (it.get("description") or "").strip(),
            "quantity": float(q) if (q := parse_amount(it.get("quantity"))) is not None else None,
            "unit_price": float(p) if (p := parse_amount(it.get("unit_price"))) is not None else None,
            "amount": float(amount) if amount is not None else None,
            "evidence": it.get("evidence"),
            "verified": bool(ok_item),
        })

    inv = ExtractedInvoice(fields=fields, line_items=items, method=method, model=model, location=location,
                           source_kind="document", document_kind=data.get("document_kind") or "invoice",
                           notes=data.get("notes"), raw=data, ocr_confidence=ocr_conf)
    inv.warnings = [f"unverified:{w}" for w in warnings]
    if ambiguous:
        inv.warnings.append("ambiguous_date")
    return inv


def extract_segment(seg: Segment, get_images: Callable[[list[int]], list[Image.Image]] | None) -> ExtractedInvoice:
    ocr_conf = _page_confidence(seg)
    any_ocr = any(p.method == "ocr" for p in seg.pages)
    location = {"pages": seg.page_numbers}
    if get_images and needs_vision(seg):
        images = get_images(seg.page_numbers[:3])
        data, model = ask_model(seg.text, images)
        return build_invoice(data, seg.text, method="llm_vision", model=model, location=location,
                             ocr_conf=ocr_conf, any_ocr=any_ocr)
    data, model = ask_model(seg.text)
    return build_invoice(data, seg.text, method="llm_text", model=model, location=location,
                         ocr_conf=ocr_conf, any_ocr=any_ocr)


def extract_layout_sheet(sheet_no: int, name: str, text: str) -> ExtractedInvoice:
    """A sheet laid out like a printed invoice: read with the model, evidence checked against the cells."""
    data, model = ask_model(f"Spreadsheet sheet '{name}' (cells separated by |):\n{text}")
    inv = build_invoice(data, text, method="llm_text", model=model, location={"sheet": name, "sheet_no": sheet_no},
                        ocr_conf=None, any_ocr=False)
    inv.source_kind = "document"
    return inv


MATH_CODES = {"LINE_ITEM_MATH", "LINE_ITEMS_MISMATCH", "TOTAL_MISMATCH"}
KEY_FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency")


def _score(inv: ExtractedInvoice) -> tuple[int, int]:
    """Lower is better: (maths problems, key fields that are empty or unproven)."""
    from .validate import validate
    math = sum(1 for i in validate(inv) if i.code in MATH_CODES)
    empty = sum(1 for n in KEY_FIELDS if inv.fields.get(n) is None or inv.fields[n].value is None)
    return math, empty


def _same_value(name: str, a, b) -> bool:
    from decimal import Decimal
    from .normalize import normalize_invoice_number, normalize_name
    if name in ("subtotal", "tax", "total"):
        return abs(Decimal(str(a)) - Decimal(str(b))) <= Decimal("0.005")
    if name == "invoice_number":
        return normalize_invoice_number(a) == normalize_invoice_number(b)
    if name in ("supplier_name", "customer_name"):
        from rapidfuzz import fuzz
        return fuzz.ratio(normalize_name(a) or "", normalize_name(b) or "") >= 92
    return str(a) == str(b)


# ---------------------------------------------------------------- dual reading for scans and photos
def _fmt(v) -> str:
    if v is None:
        return "empty"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return f"{v:,.2f}" if type(v).__name__ == "Decimal" else str(v)


def reconcile(text_inv: ExtractedInvoice, image_inv: ExtractedInvoice) -> ExtractedInvoice:
    """Two independent readings of a scanned page: (1) OCR text -> AI, (2) page image -> AI.
    Agreement confirms a value. Disagreement on amounts is settled by the arithmetic (subtotal + tax = total,
    line items = subtotal); anything still unresolved is flagged with both readings for a person."""
    from .validate import validate
    fields: dict[str, FieldValue] = {}
    disagreements: list[tuple[str, object, object]] = []
    for name in KEY_FIELDS:
        t = text_inv.fields.get(name) or FieldValue(None)
        v = image_inv.fields.get(name) or FieldValue(None)
        if t.value is None and v.value is None:
            fields[name] = t
        elif t.value is None:
            if t.suggested is not None and _same_value(name, t.suggested, v.value):
                fields[name] = FieldValue(v.value, evidence=v.evidence or t.evidence, raw=v.raw, verified=True,
                                          confidence=0.9, source="vision+text")
            else:
                fields[name] = v          # only the image could read it (flagged as read from the image)
        elif v.value is None:
            fields[name] = t
        elif _same_value(name, t.value, v.value):
            fields[name] = FieldValue(t.value, evidence=t.evidence, raw=t.raw, verified=t.verified if t.verified else True,
                                      confidence=max(t.confidence, 0.99 if t.verified else 0.9), source="vision+text")
        else:
            disagreements.append((name, t.value, v.value))
            strong_text = bool(t.verified) and t.confidence >= 0.9
            fields[name] = t if strong_text else v

    merged = ExtractedInvoice(fields=fields, line_items=list(text_inv.line_items), method="llm_dual",
                              model=image_inv.model or text_inv.model, location=text_inv.location,
                              source_kind=text_inv.source_kind, document_kind=text_inv.document_kind,
                              notes=text_inv.notes or image_inv.notes, raw={"text": text_inv.raw, "image": image_inv.raw},
                              ocr_confidence=text_inv.ocr_confidence)

    # amounts and line items: keep the combination that passes more checks
    def score(inv):
        return sum(1 for i in validate(inv) if i.code in MATH_CODES)

    amount_names = ("subtotal", "tax", "total")
    candidates = []
    for amounts_from in ("chosen", "text", "image"):
        for items_from in ("text", "image"):
            c = ExtractedInvoice(fields=dict(fields), line_items=list(text_inv.line_items if items_from == "text"
                                                                       else image_inv.line_items),
                                 source_kind=merged.source_kind, location=merged.location)
            if amounts_from != "chosen":
                src = text_inv if amounts_from == "text" else image_inv
                for a in amount_names:
                    if src.fields.get(a) is not None and src.fields[a].value is not None:
                        c.fields[a] = src.fields[a]
            missing = sum(1 for it in c.line_items if it.get("amount") is None)
            # fewer maths problems first; then complete items (an empty or amount-less list must not "pass"
            # just because there is nothing to check); then the longer list; then prefer the text reading
            candidates.append(((score(c), missing, -len(c.line_items)), amounts_from != "chosen", items_from != "text", c))
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    best = candidates[0][3]
    merged.fields, merged.line_items = best.fields, best.line_items

    for name, tv, vv in disagreements:
        chosen = merged.fields[name].value
        if name in amount_names and candidates[0][0][0] == 0:
            continue  # settled by the arithmetic: the chosen value makes every total add up
        merged.warnings.append(f"disagree:{name}:{_fmt(tv)}|{_fmt(vv)}|{_fmt(chosen)}")
    return merged
