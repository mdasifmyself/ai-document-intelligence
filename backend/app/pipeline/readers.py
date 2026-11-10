"""Turn PDFs and images into page text.

PDF: every page is checked on its own. Pages with a real text layer are read directly (fast, exact);
pages without one (scans) are rendered and sent to OCR. So mixed PDFs work too.
Images: JPG, PNG and multi-page TIFF go to OCR. Damaged-but-readable images are read with a warning.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium
from PIL import Image, ImageFile, ImageSequence, UnidentifiedImageError

from ..config import get_settings
from .detect import ProcessingError
from .ocr import ocr_image

MIN_TEXT_CHARS = 40          # fewer real characters than this on a page = treat it as a scan
MAX_OCR_SIDE = 3200          # very large photos are scaled down first; OCR gains nothing above this

Progress = Callable[[str, int, int], None]


@dataclass
class Page:
    page_no: int
    text: str
    method: str                       # digital | ocr | error
    ocr_confidence: float | None = None
    rotation: int | None = None
    deskew_angle: float | None = None
    label: str | None = None
    warnings: list[str] = field(default_factory=list)


def _visible_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text or ""))


def open_pdf(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        msg = str(e).lower()
        if "password" in msg:
            raise ProcessingError("PASSWORD_PROTECTED", "The PDF is password-protected. Upload an unlocked copy.")
        raise ProcessingError("CORRUPTED_FILE", "The PDF is damaged and cannot be opened.")


def render_pdf_page(pdf: pdfium.PdfDocument, index: int, dpi: int) -> Image.Image:
    return pdf[index].render(scale=dpi / 72).to_pil()


def read_pdf(path: Path, progress: Progress | None = None) -> list[Page]:
    s = get_settings()
    pdf = open_pdf(path)
    n = len(pdf)
    if n == 0:
        raise ProcessingError("EMPTY_DOCUMENT", "The PDF has no pages.")
    if n > s.max_pages:
        raise ProcessingError("TOO_MANY_PAGES", f"The PDF has {n} pages; the limit is {s.max_pages}.")
    pages: list[Page] = []
    for i in range(n):
        try:
            page = pdf[i]
            text = page.get_textpage().get_text_range() or ""
        except Exception:  # one broken page must not stop the document
            pages.append(Page(i + 1, "", "error", warnings=["This page could not be read."]))
            continue
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if _visible_chars(text) >= MIN_TEXT_CHARS:
            pages.append(Page(i + 1, text.strip(), "digital"))
        else:
            img = render_pdf_page(pdf, i, s.ocr_dpi)
            r = ocr_image(img)
            pages.append(Page(i + 1, r.text, "ocr", r.confidence, r.rotation, r.deskew_angle))
        if progress and (i % 5 == 0 or i == n - 1):
            progress("reading", i + 1, n)
    pdf.close()
    return pages


def _load_image(path: Path) -> tuple[Image.Image, bool]:
    """Returns (image, damaged). Truncated files are read as far as possible."""
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        img = Image.open(path)
        img.load()
        return img, False
    except UnidentifiedImageError:
        raise ProcessingError("CORRUPTED_FILE", "The image is damaged or not a real image file.")
    except (OSError, SyntaxError):
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            img = Image.open(path)
            img.load()
            return img, True
        except Exception:
            raise ProcessingError("CORRUPTED_FILE", "The image is damaged and cannot be read.")
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = False


def iter_image_frames(path: Path):
    img, damaged = _load_image(path)
    frames = [f.copy() for f in ImageSequence.Iterator(img)] if getattr(img, "n_frames", 1) > 1 else [img]
    return frames, damaged


def shrink(img: Image.Image, side: int = MAX_OCR_SIDE) -> Image.Image:
    if max(img.size) > side:
        img = img.copy()
        img.thumbnail((side, side))
    return img


def read_image(path: Path, progress: Progress | None = None) -> list[Page]:
    s = get_settings()
    frames, damaged = iter_image_frames(path)
    if len(frames) > s.max_pages:
        raise ProcessingError("TOO_MANY_PAGES", f"The image has {len(frames)} pages; the limit is {s.max_pages}.")
    pages = []
    for i, frame in enumerate(frames):
        r = ocr_image(shrink(frame))
        p = Page(i + 1, r.text, "ocr", r.confidence, r.rotation, r.deskew_angle)
        if damaged:
            p.warnings.append("The image file is damaged; only the readable part was processed.")
        pages.append(p)
        if progress:
            progress("reading", i + 1, len(frames))
    return pages


def page_image(path: Path, file_type: str, page_no: int, dpi: int = 110) -> Image.Image:
    """Image of one page, for previews in the UI and for the AI vision fallback."""
    if file_type == "pdf":
        pdf = open_pdf(path)
        try:
            if not 1 <= page_no <= len(pdf):
                raise ProcessingError("NOT_FOUND", "Page does not exist.")
            return render_pdf_page(pdf, page_no - 1, dpi)
        finally:
            pdf.close()
    frames, _ = iter_image_frames(path)
    if not 1 <= page_no <= len(frames):
        raise ProcessingError("NOT_FOUND", "Page does not exist.")
    img = frames[page_no - 1].convert("RGB")
    target = int(11 * dpi)  # about the height of a letter page at this dpi
    if max(img.size) > target:
        img.thumbnail((target, target))
    return img
