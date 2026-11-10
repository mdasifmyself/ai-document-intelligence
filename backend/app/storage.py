"""File storage on a mounted volume. Files are stored under a random name; the original name is only kept in the database."""
import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile

from .config import get_settings

CHUNK = 1024 * 1024


class TooLarge(Exception):
    pass


def save_upload(upload: UploadFile) -> tuple[Path, int, str]:
    """Stream the upload to disk, enforcing the size limit. Returns (path, size, sha256)."""
    s = get_settings()
    limit = s.max_file_mb * 1024 * 1024
    folder = Path(s.storage_dir)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix.lower()[:10]
    path = folder / f"{uuid.uuid4().hex}{suffix}"
    h = hashlib.sha256()
    size = 0
    with open(path, "wb") as out:
        while True:
            chunk = upload.file.read(CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                out.close()
                path.unlink(missing_ok=True)
                raise TooLarge()
            h.update(chunk)
            out.write(chunk)
    return path, size, h.hexdigest()


def copy_into_storage(src: Path) -> tuple[Path, int, str]:
    s = get_settings()
    folder = Path(s.storage_dir)
    folder.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    path = folder / f"{uuid.uuid4().hex}{src.suffix.lower()}"
    path.write_bytes(data)
    return path, len(data), hashlib.sha256(data).hexdigest()
