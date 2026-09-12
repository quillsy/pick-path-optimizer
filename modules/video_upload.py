import os
import hashlib
import tempfile
from dataclasses import dataclass
from contextlib import contextmanager
from typing import Optional, Iterator, Tuple

MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024

@dataclass(frozen=True)
class UploadedVideoInfo:
    original_filename: str
    suffix: str
    size_bytes: int
    sha256: str
    mime_type: Optional[str]

@contextmanager
def temporary_uploaded_video(original_filename: str, file_bytes: bytes, mime_type: Optional[str] = None) -> Iterator[Tuple[str, UploadedVideoInfo]]:
    if not file_bytes:
        raise ValueError("Die hochgeladene Datei ist leer.")

    size_bytes = len(file_bytes)
    if size_bytes > MAX_VIDEO_SIZE_BYTES:
        raise ValueError(f"Die Datei überschreitet das Limit von {MAX_VIDEO_SIZE_BYTES // (1024*1024)} MiB.")

    _, ext = os.path.splitext(original_filename)
    suffix = ext.lower()

    if suffix not in [".mp4", ".mov", ".m4v"]:
        raise ValueError(f"Nicht unterstützte Dateiendung: {suffix}")

    expected_sha256 = hashlib.sha256(file_bytes).hexdigest()

    fd, temp_path = tempfile.mkstemp(prefix="video_", suffix=suffix)
    primary_exception = None
    try:
        with open(fd, "wb") as f:
            f.write(file_bytes)
            f.flush()
            os.fsync(f.fileno())

        actual_size = os.path.getsize(temp_path)
        if actual_size != size_bytes:
            raise RuntimeError("Integritätsprüfung fehlgeschlagen: Geschriebene Dateigröße stimmt nicht überein.")

        sha256_hash = hashlib.sha256()
        with open(temp_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        actual_sha256 = sha256_hash.hexdigest()

        if actual_sha256 != expected_sha256:
            raise RuntimeError("Integritätsprüfung fehlgeschlagen: SHA-256 stimmt nicht mit dem Upload überein.")

        info = UploadedVideoInfo(
            original_filename=original_filename,
            suffix=suffix,
            size_bytes=actual_size,
            sha256=actual_sha256,
            mime_type=mime_type
        )

        try:
            yield temp_path, info
        except Exception as e:
            primary_exception = e
            raise

    except Exception as e:
        if primary_exception is None:
            primary_exception = e
        raise
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as cleanup_err:
                if primary_exception is None:
                    raise cleanup_err
