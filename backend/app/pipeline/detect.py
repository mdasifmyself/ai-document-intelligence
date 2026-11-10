"""Find the real file type from its first bytes, not from its name.

A renamed or damaged file is caught here, before any reader touches it.
"""
import zipfile
from dataclasses import dataclass
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}


class ProcessingError(Exception):
    """A known, user-facing failure. `code` is stable and shown in the UI and API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Detected:
    file_type: str   # pdf | image | xlsx | xls | csv
    mime: str


def detect(path: Path, filename: str) -> Detected:
    ext = Path(filename).suffix.lower()
    size = path.stat().st_size
    if size == 0:
        raise ProcessingError("EMPTY_FILE", "The file is empty (0 bytes).")
    with open(path, "rb") as f:
        head = f.read(2048)

    if b"%PDF-" in head[:1024]:
        return Detected("pdf", "application/pdf")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Detected("image", "image/png")
    if head.startswith(b"\xff\xd8\xff"):
        return Detected("image", "image/jpeg")
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return Detected("image", "image/tiff")
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return Detected("xls", "application/vnd.ms-excel")
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            raise ProcessingError("CORRUPTED_FILE", "The spreadsheet is damaged and cannot be opened.")
        if "xl/workbook.xml" in names:
            return Detected("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        raise ProcessingError("UNSUPPORTED_TYPE", "This ZIP-based file is not an Excel workbook.")
    if ext == ".csv" or _looks_like_text(head):
        if ext in (".csv", ".txt") or b"," in head or b";" in head:
            return Detected("csv", "text/csv")

    if ext in ALLOWED_EXTENSIONS:
        raise ProcessingError("CORRUPTED_FILE", f"The file is named {ext} but its content is not a valid {ext[1:].upper()} file.")
    raise ProcessingError("UNSUPPORTED_TYPE", f"File type {ext or '(none)'} is not supported.")


def _looks_like_text(head: bytes) -> bool:
    if not head or b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            head.decode("cp1252")
            return sum(c < 9 for c in head) == 0
        except UnicodeDecodeError:
            return False
