import os
import math
import hashlib
import tempfile
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Iterator
from contextlib import contextmanager

from modules.video_frames import ExtractedFrame

class VideoROIError(Exception):
    pass

@dataclass(frozen=True)
class NormalizedROI:
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self):
        for val, name in [
            (self.left, "left"),
            (self.top, "top"),
            (self.right, "right"),
            (self.bottom, "bottom"),
        ]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"{name} muss eine Zahl sein.")
            if not math.isfinite(val):
                raise ValueError(f"{name} muss endlich sein.")
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} muss zwischen 0.0 und 1.0 liegen.")

        if self.left >= self.right:
            raise ValueError("left muss kleiner als right sein.")
        if self.top >= self.bottom:
            raise ValueError("top muss kleiner als bottom sein.")


@dataclass(frozen=True)
class PixelROI:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ROICrop:
    sequence_index: int
    timestamp_seconds: float
    source_frame_path: str
    crop_path: str
    pixel_roi: PixelROI
    size_bytes: int
    sha256: str


def roi_to_pixels(roi: NormalizedROI, frame_width: int, frame_height: int) -> PixelROI:
    if not isinstance(frame_width, int) or isinstance(frame_width, bool) or frame_width <= 0:
        raise ValueError("frame_width muss ein positiver Integer sein.")
    if not isinstance(frame_height, int) or isinstance(frame_height, bool) or frame_height <= 0:
        raise ValueError("frame_height muss ein positiver Integer sein.")

    # Rundungsstrategie: Startkoordinaten (left/top) abrunden (floor), Endkoordinaten aufrunden (ceil)
    x_raw = math.floor(roi.left * frame_width)
    y_raw = math.floor(roi.top * frame_height)
    r_raw = math.ceil(roi.right * frame_width)
    b_raw = math.ceil(roi.bottom * frame_height)

    # Auf Bildgrenzen clampen
    x = max(0, min(frame_width - 1, x_raw))
    y = max(0, min(frame_height - 1, y_raw))
    r = max(1, min(frame_width, r_raw))
    b = max(1, min(frame_height, b_raw))

    # Mindestens 1 Pixel Breite/Höhe
    width = max(1, r - x)
    height = max(1, b - y)

    # Korrektur, falls width/height über Bildrand ragt
    if x + width > frame_width:
        x = frame_width - width
    if y + height > frame_height:
        y = frame_height - height

    return PixelROI(x=x, y=y, width=width, height=height)


@contextmanager
def temporary_roi_crops(
    frames: List[ExtractedFrame],
    roi: NormalizedROI,
    frame_width: int,
    frame_height: int
) -> Iterator[List[ROICrop]]:

    pixel_roi = roi_to_pixels(roi, frame_width, frame_height)
    temp_dir = tempfile.mkdtemp(prefix="video_crops_")
    primary_exception = None

    try:
        crops = []
        for frame in frames:
            crop_filename = f"crop_{frame.sequence_index:04d}.jpg"
            crop_path = os.path.join(temp_dir, crop_filename)

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v", "error",
                        "-i", frame.path,
                        "-vf", f"crop={pixel_roi.width}:{pixel_roi.height}:{pixel_roi.x}:{pixel_roi.y}",
                        "-frames:v", "1",
                        "-y",
                        crop_path
                    ],
                    shell=False,
                    check=True,
                    timeout=30
                )
            except FileNotFoundError:
                raise VideoROIError("ffmpeg ist nicht installiert oder nicht im PATH.")
            except subprocess.TimeoutExpired:
                raise VideoROIError("ffmpeg Zeitüberschreitung beim Croppen.")
            except subprocess.CalledProcessError as e:
                raise VideoROIError(f"ffmpeg Fehler beim Croppen (Code {e.returncode}).")

            if not os.path.exists(crop_path):
                raise VideoROIError("Crop-Datei wurde von ffmpeg nicht erstellt.")

            size = os.path.getsize(crop_path)
            if size == 0:
                raise VideoROIError("Crop-Datei ist leer (0 Bytes).")

            with open(crop_path, "rb") as f:
                sha256 = hashlib.sha256(f.read()).hexdigest()

            crops.append(
                ROICrop(
                    sequence_index=frame.sequence_index,
                    timestamp_seconds=frame.timestamp_seconds,
                    source_frame_path=frame.path,
                    crop_path=crop_path,
                    pixel_roi=pixel_roi,
                    size_bytes=size,
                    sha256=sha256
                )
            )

        yield crops

    except BaseException as e:
        primary_exception = e
        raise
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception as cleanup_error:
            if primary_exception is None:
                raise cleanup_error
