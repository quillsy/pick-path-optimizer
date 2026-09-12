import json
import subprocess
import math
import os
import hashlib
import tempfile
import shutil
from dataclasses import dataclass
from typing import Optional, Iterator, List
from contextlib import contextmanager

FRAME_SAMPLE_INTERVAL_SECONDS = 0.5
MAX_EXTRACTED_FRAMES = 300
MAX_PREVIEW_FRAMES = 12
FFMPEG_TIMEOUT_SECONDS = 30

@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int
    fps: float
    frame_count: Optional[int]
    video_codec: Optional[str]
    container_format: Optional[str]

@dataclass(frozen=True)
class ExtractedFrame:
    sequence_index: int
    timestamp_seconds: float
    path: str
    size_bytes: int
    sha256: str

class VideoFramesError(Exception):
    pass

def probe_video(video_path: str) -> VideoMetadata:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", video_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
    except FileNotFoundError:
        raise VideoFramesError("ffprobe ist nicht auf dem System installiert oder nicht im PATH.")
    except subprocess.TimeoutExpired:
        raise VideoFramesError("ffprobe hat das Zeitlimit überschritten.")

    if result.returncode != 0:
        raise VideoFramesError(f"ffprobe endete mit einem Fehler (Code {result.returncode}).")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise VideoFramesError("ffprobe gab ungültiges JSON zurück.")

    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]

    if not video_streams:
        raise VideoFramesError("Kein Video-Stream in der Datei gefunden.")

    v_stream = video_streams[0]
    format_info = data.get("format", {})

    try:
        duration_str = v_stream.get("duration") or format_info.get("duration")
        if duration_str is None:
            raise ValueError()
        duration_seconds = float(duration_str)
    except (ValueError, TypeError):
        raise VideoFramesError("Videodauer (duration) fehlt oder ist ungültig.")

    if duration_seconds <= 0:
        raise VideoFramesError("Videodauer muss positiv sein.")

    try:
        width = int(v_stream.get("width", 0))
        height = int(v_stream.get("height", 0))
    except (ValueError, TypeError):
        raise VideoFramesError("Video-Dimensionen (width/height) sind ungültig.")

    if width <= 0 or height <= 0:
        raise VideoFramesError("Video-Dimensionen müssen positiv sein.")

    fps_str = v_stream.get("r_frame_rate")
    fps = None
    if fps_str:
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/", 1)
                fps = float(num) / float(den)
            else:
                fps = float(fps_str)
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    if fps is None or math.isnan(fps) or math.isinf(fps) or fps <= 0:
        raise VideoFramesError("Video-FPS ist ungültig oder konnte nicht ermittelt werden.")

    frame_count = None
    fc_str = v_stream.get("nb_frames")
    if fc_str is not None:
        try:
            fc_val = int(fc_str)
            if fc_val > 0:
                frame_count = fc_val
        except (ValueError, TypeError):
            pass

    return VideoMetadata(
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        video_codec=v_stream.get("codec_name"),
        container_format=format_info.get("format_name")
    )

def calculate_sample_timestamps(
    duration_seconds: float,
    interval_seconds: float = FRAME_SAMPLE_INTERVAL_SECONDS,
    max_frames: int = MAX_EXTRACTED_FRAMES
) -> List[float]:
    if not isinstance(max_frames, int) or isinstance(max_frames, bool) or max_frames <= 0:
        raise ValueError("max_frames muss ein positiver Integer sein.")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds muss positiv sein.")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds muss positiv sein.")

    raw_samples = []
    current = 0.0
    while current < duration_seconds:
        raw_samples.append(current)
        current += interval_seconds

    if not raw_samples:
        return [0.0]

    if len(raw_samples) <= max_frames:
        return raw_samples

    # We have more samples than max_frames. Select evenly.
    # We want exactly max_frames samples, starting with the first, ending with the last possible.
    indices = [int(round(i * (len(raw_samples) - 1) / (max_frames - 1))) for i in range(max_frames)]

    selected_samples = [raw_samples[i] for i in indices]

    # Remove any potential duplicates (due to rounding) while preserving order
    final_samples = []
    seen = set()
    for s in selected_samples:
        if s not in seen:
            final_samples.append(s)
            seen.add(s)

    return final_samples

def select_preview_frames(frames: List[ExtractedFrame], max_preview: int = MAX_PREVIEW_FRAMES) -> List[ExtractedFrame]:
    if not isinstance(max_preview, int) or isinstance(max_preview, bool) or max_preview <= 0:
        raise ValueError("max_preview muss ein positiver Integer sein.")

    if len(frames) <= max_preview:
        return list(frames)

    indices = [int(round(i * (len(frames) - 1) / (max_preview - 1))) for i in range(max_preview)]

    selected = []
    seen = set()
    for i in indices:
        if i not in seen:
            selected.append(frames[i])
            seen.add(i)

    return selected

@contextmanager
def temporary_extracted_frames(video_path: str, timestamps: List[float]) -> Iterator[List[ExtractedFrame]]:
    if len(timestamps) > MAX_EXTRACTED_FRAMES:
        raise VideoFramesError(f"Maximal {MAX_EXTRACTED_FRAMES} Frames erlaubt.")

    for ts in timestamps:
        if ts < 0:
            raise VideoFramesError("Timestamp darf nicht negativ sein.")

    temp_dir = tempfile.mkdtemp(prefix="video_frames_")
    primary_exception = None
    frames = []

    try:
        for idx, ts in enumerate(timestamps):
            out_path = os.path.join(temp_dir, f"frame_{idx:04d}.jpg")
            try:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-v", "error",
                        "-ss", str(ts),
                        "-i", video_path,
                        "-frames:v", "1",
                        "-q:v", "2",
                        "-y",
                        out_path
                    ],
                    capture_output=True,
                    text=True,
                    timeout=FFMPEG_TIMEOUT_SECONDS,
                    check=False
                )
            except FileNotFoundError:
                raise VideoFramesError("ffmpeg ist nicht auf dem System installiert oder nicht im PATH.")
            except subprocess.TimeoutExpired:
                raise VideoFramesError(f"ffmpeg Timeout beim Extrahieren von Frame {idx}.")

            if result.returncode != 0:
                raise VideoFramesError(f"ffmpeg Fehler beim Extrahieren von Frame {idx}: Code {result.returncode}")

            if not os.path.exists(out_path):
                raise VideoFramesError(f"Outputdatei für Frame {idx} fehlt.")

            size = os.path.getsize(out_path)
            if size == 0:
                raise VideoFramesError(f"Outputdatei für Frame {idx} ist leer.")

            sha256_hash = hashlib.sha256()
            with open(out_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)

            frames.append(ExtractedFrame(
                sequence_index=idx,
                timestamp_seconds=ts,
                path=out_path,
                size_bytes=size,
                sha256=sha256_hash.hexdigest()
            ))

        try:
            yield frames
        except BaseException as e:
            primary_exception = e
            raise

    except BaseException as e:
        if primary_exception is None:
            primary_exception = e
        raise
    finally:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except BaseException as cleanup_err:
                if primary_exception is None:
                    raise cleanup_err
