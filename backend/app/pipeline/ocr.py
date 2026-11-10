"""OCR for scans and photos: clean the image, fix rotation and tilt, then read it with Tesseract.

Two passes: a light clean-up first; if Tesseract is unsure (low mean confidence), a stronger
clean-up (adaptive threshold) is tried and the better result is kept.
"""
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from PIL import Image

from ..config import get_settings


@dataclass
class OcrResult:
    text: str
    confidence: float        # mean word confidence 0-100
    rotation: int            # degrees turned before reading (0/90/180/270)
    deskew_angle: float      # small tilt corrected, in degrees
    word_count: int


def _to_gray(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def _upscale(gray: np.ndarray, target: int = 1800) -> np.ndarray:
    h, w = gray.shape
    longest = max(h, w)
    if longest < target:
        f = target / longest
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    return gray


def _fix_rotation(gray: np.ndarray) -> tuple[np.ndarray, int]:
    """Turn pages that were scanned sideways or upside down (Tesseract orientation detection)."""
    try:
        osd = pytesseract.image_to_osd(gray, config="--psm 0", output_type=pytesseract.Output.DICT)
        angle = int(osd.get("rotate", 0)) % 360
        if osd.get("orientation_conf", 0) < 1.5:
            return gray, 0
    except pytesseract.TesseractError:
        return gray, 0
    if angle == 90:
        return cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE), 90
    if angle == 180:
        return cv2.rotate(gray, cv2.ROTATE_180), 180
    if angle == 270:
        return cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE), 270
    return gray, 0


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """Find a small tilt (up to ±6°) with a projection-profile search and straighten it."""
    small = gray
    h, w = gray.shape
    if max(h, w) > 1000:
        f = 1000 / max(h, w)
        small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    inv = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    sh, sw = inv.shape
    center = (sw / 2, sh / 2)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-6, 6.01, 0.5):
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(inv, m, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    if abs(best_angle) < 0.25:
        return gray, 0.0
    m = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    out = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, best_angle


def _light_clean(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return cv2.medianBlur(clahe.apply(gray), 3)


def _strong_clean(gray: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


def _read(img: np.ndarray, lang: str) -> tuple[str, float, int]:
    data = pytesseract.image_to_data(img, lang=lang, config="--oem 1 --psm 3 -c preserve_interword_spaces=1",
                                     output_type=pytesseract.Output.DICT)
    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        confs.append(conf)
    text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
    mean = float(np.mean(confs)) if confs else 0.0
    return text, mean, len(confs)


def ocr_image(img: Image.Image) -> OcrResult:
    s = get_settings()
    gray = _upscale(_to_gray(img))
    gray, rotation = _fix_rotation(gray)
    gray, angle = _deskew(gray)
    text, conf, words = _read(_light_clean(gray), s.ocr_lang)
    if conf < 75:
        text2, conf2, words2 = _read(_strong_clean(gray), s.ocr_lang)
        if conf2 > conf and words2 >= words * 0.6:
            text, conf, words = text2, conf2, words2
    return OcrResult(text=text, confidence=round(conf, 1), rotation=rotation, deskew_angle=angle, word_count=words)
