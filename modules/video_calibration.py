import io
import json
import zipfile
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List

from modules.video_frames import ExtractedFrame, VideoMetadata
from modules.video_roi import ROICrop, NormalizedROI, PixelROI

class CalibrationPackageError(Exception):
    pass

@dataclass(frozen=True)
class CalibrationFrame:
    sequence_index: int
    timestamp_seconds: float
    original_filename: str
    crop_filename: str
    original_size_bytes: int
    crop_size_bytes: int
    original_sha256: str
    crop_sha256: str
    pixel_roi: PixelROI
    source_original_path: str
    source_crop_path: str


def select_calibration_pairs(frames: List[ExtractedFrame], crops: List[ROICrop], max_pairs: int = 8) -> List[CalibrationFrame]:
    if type(max_pairs) is not int or type(max_pairs) is bool or max_pairs <= 0:
        raise ValueError("max_pairs muss ein int > 0 sein")

    frame_dict = {}
    for f in frames:
        if f.sequence_index in frame_dict:
            raise ValueError(f"Doppelter sequence_index {f.sequence_index} in frames")
        frame_dict[f.sequence_index] = f

    crop_dict = {}
    for c in crops:
        if c.sequence_index in crop_dict:
            raise ValueError(f"Doppelter sequence_index {c.sequence_index} in crops")
        crop_dict[c.sequence_index] = c

    if not frame_dict and not crop_dict:
        return []

    if not frame_dict or not crop_dict or len(frame_dict) != len(crop_dict):
        raise ValueError("Unterschiedliche Anzahl von frames und crops oder eine Seite ist leer")

    pairs = []
    for seq in frame_dict.keys():
        if seq not in crop_dict:
            raise ValueError(f"Crop fehlt für frame {seq}")
        f = frame_dict[seq]
        c = crop_dict[seq]
        if f.timestamp_seconds != c.timestamp_seconds:
            raise ValueError(f"Timestamp Mismatch für frame {seq}")
        pairs.append(CalibrationFrame(
            sequence_index=seq,
            timestamp_seconds=f.timestamp_seconds,
            original_filename=f"original/frame_{seq:04d}.jpg",
            crop_filename=f"crop/frame_{seq:04d}.jpg",
            original_size_bytes=f.size_bytes,
            crop_size_bytes=c.size_bytes,
            original_sha256=f.sha256,
            crop_sha256=c.sha256,
            pixel_roi=c.pixel_roi,
            source_original_path=f.path,
            source_crop_path=c.crop_path
        ))

    pairs.sort(key=lambda p: (p.timestamp_seconds, p.sequence_index))

    if len(pairs) <= max_pairs:
        return pairs

    if max_pairs == 1:
        return [pairs[0]]

    selected = [pairs[0]]
    n = max_pairs - 2
    if n > 0:
        pool = pairs[1:-1]
        for i in range(n):
            if n == 1:
                idx = len(pool) // 2
            else:
                idx = int(round(i * (len(pool) - 1) / (n - 1)))
            selected.append(pool[idx])

    selected.append(pairs[-1])
    return selected

MAX_CALIBRATION_ZIP_BYTES = 50 * 1024 * 1024

def build_calibration_zip(
    selected_pairs: List[CalibrationFrame],
    video_metadata: VideoMetadata,
    normalized_roi: NormalizedROI,
    original_video_name: str,
    max_bytes: int = MAX_CALIBRATION_ZIP_BYTES
) -> bytes:
    if type(max_bytes) is not int or type(max_bytes) is bool or max_bytes <= 0:
        raise ValueError("max_bytes muss ein int > 0 sein")

    if not selected_pairs:
        raise CalibrationPackageError("Keine Kalibrierungsframes vorhanden.")

    ref_roi = selected_pairs[0].pixel_roi
    for pair in selected_pairs:
        if pair.pixel_roi != ref_roi:
            raise CalibrationPackageError("Unterschiedliche PixelROI innerhalb selected_pairs")

    out_buf = io.BytesIO()

    with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest_frames = []
        for pair in selected_pairs:
            try:
                with open(pair.source_original_path, "rb") as f:
                    orig_bytes = f.read()
                with open(pair.source_crop_path, "rb") as f:
                    crop_bytes = f.read()
            except OSError:
                raise CalibrationPackageError("Fehler beim Lesen der Quelldateien.")

            actual_orig_size = len(orig_bytes)
            actual_crop_size = len(crop_bytes)

            if actual_orig_size == 0 or actual_crop_size == 0:
                raise CalibrationPackageError("Quelldatei ist leer.")

            actual_orig_sha = hashlib.sha256(orig_bytes).hexdigest()
            actual_crop_sha = hashlib.sha256(crop_bytes).hexdigest()

            if (actual_orig_size != pair.original_size_bytes or
                actual_crop_size != pair.crop_size_bytes or
                actual_orig_sha != pair.original_sha256 or
                actual_crop_sha != pair.crop_sha256):
                raise CalibrationPackageError("Quelldatei hat sich seit der Frame-Erzeugung verändert.")

            zf.writestr(pair.original_filename, orig_bytes)
            zf.writestr(pair.crop_filename, crop_bytes)

            manifest_frames.append({
                "sequence_index": pair.sequence_index,
                "timestamp_seconds": pair.timestamp_seconds,
                "original_file": pair.original_filename,
                "crop_file": pair.crop_filename,
                "original_size_bytes": actual_orig_size,
                "crop_size_bytes": actual_crop_size,
                "original_sha256": actual_orig_sha,
                "crop_sha256": actual_crop_sha
            })

            if out_buf.tell() > max_bytes:
                raise CalibrationPackageError("ZIP überschreitet Maximalgröße")

        manifest = {
            "schema_version": 1,
            "purpose": "pick_video_calibration",
            "original_video_name": original_video_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "video": {
                "duration_seconds": video_metadata.duration_seconds,
                "width": video_metadata.width,
                "height": video_metadata.height,
                "fps": video_metadata.fps,
                "codec": video_metadata.video_codec,
                "container": video_metadata.container_format
            },
            "roi": {
                "normalized": {
                    "left": normalized_roi.left,
                    "top": normalized_roi.top,
                    "right": normalized_roi.right,
                    "bottom": normalized_roi.bottom
                },
                "pixel": {
                    "x": ref_roi.x,
                    "y": ref_roi.y,
                    "width": ref_roi.width,
                    "height": ref_roi.height
                }
            },
            "frames": manifest_frames
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False).encode('utf-8'))

    final_bytes = out_buf.getvalue()
    if len(final_bytes) > max_bytes:
        raise CalibrationPackageError("ZIP überschreitet Maximalgröße")

    verify_calibration_zip(final_bytes)
    return final_bytes

import re
import math

import re
import math

def verify_calibration_zip(zip_bytes: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            namelist = zf.namelist()
            if len(namelist) != len(set(namelist)):
                raise CalibrationPackageError("Doppelter ZIP-Eintrag")

            for name in namelist:
                if ".." in name or name.startswith("/") or "\\" in name:
                    raise CalibrationPackageError("Gefährlicher Pfad im ZIP")

            if "manifest.json" not in namelist:
                raise CalibrationPackageError("manifest.json fehlt im ZIP")

            try:
                manifest_bytes = zf.read("manifest.json")
                manifest = json.loads(manifest_bytes.decode('utf-8'))
            except Exception:
                raise CalibrationPackageError("manifest.json ist kein gültiges JSON")

            if type(manifest) is not dict:
                raise CalibrationPackageError("Manifest ist kein JSON Object")

            if manifest.get("schema_version") != 1:
                raise CalibrationPackageError("Unbekannte schema_version")

            if manifest.get("purpose") != "pick_video_calibration":
                raise CalibrationPackageError("Falscher purpose im Manifest")

            if type(manifest.get("video")) is not dict or type(manifest.get("roi")) is not dict:
                raise CalibrationPackageError("Manifest video oder roi ist kein dict")

            frames = manifest.get("frames")
            if type(frames) is not list:
                raise CalibrationPackageError("frames ist keine Liste")

            expected_names = {"manifest.json"}
            seen_seqs = set()
            seen_originals = set()
            seen_crops = set()

            last_ts = -1.0
            last_seq = -1

            for mf in frames:
                if type(mf) is not dict:
                    raise CalibrationPackageError("Frameeintrag ist kein Object")

                seq = mf.get("sequence_index")
                if type(seq) is not int or type(seq) is bool or seq < 0:
                    raise CalibrationPackageError("Ungültiger sequence_index")
                if seq in seen_seqs:
                    raise CalibrationPackageError("Doppelter sequence_index im Manifest")
                seen_seqs.add(seq)

                ts = mf.get("timestamp_seconds")
                if type(ts) not in (int, float) or type(ts) is bool or not math.isfinite(ts) or ts < 0:
                    raise CalibrationPackageError("Ungültiger timestamp_seconds")

                if ts < last_ts or (ts == last_ts and seq <= last_seq):
                    raise CalibrationPackageError("Frame-Reihenfolge nicht zeitlich aufsteigend")
                last_ts = ts
                last_seq = seq

                orig_file = mf.get("original_file")
                crop_file = mf.get("crop_file")

                if type(orig_file) is not str or not re.fullmatch(r"original/frame_\d{4}\.jpg", orig_file):
                    raise CalibrationPackageError("Ungültiger original_file Pfad")
                if type(crop_file) is not str or not re.fullmatch(r"crop/frame_\d{4}\.jpg", crop_file):
                    raise CalibrationPackageError("Ungültiger crop_file Pfad")

                if orig_file in seen_originals:
                    raise CalibrationPackageError("Doppelter original_file-Verweis")
                seen_originals.add(orig_file)
                if crop_file in seen_crops:
                    raise CalibrationPackageError("Doppelter crop_file-Verweis")
                seen_crops.add(crop_file)

                expected_names.add(orig_file)
                expected_names.add(crop_file)

                for size_key in ("original_size_bytes", "crop_size_bytes"):
                    sz = mf.get(size_key)
                    if type(sz) is not int or type(sz) is bool or sz <= 0:
                        raise CalibrationPackageError(f"Ungültige {size_key}")

                for hash_key in ("original_sha256", "crop_sha256"):
                    h = mf.get(hash_key)
                    if type(h) is not str or not re.fullmatch(r"[a-f0-9]{64}", h):
                        raise CalibrationPackageError(f"Ungültiges {hash_key}")

            if set(namelist) != expected_names:
                raise CalibrationPackageError("Dateimenge im ZIP entspricht nicht den Erwartungen des Manifests")

            for mf in frames:
                for f_key, size_key, hash_key in [("original_file", "original_size_bytes", "original_sha256"), ("crop_file", "crop_size_bytes", "crop_sha256")]:
                    fname = mf.get(f_key)
                    data = zf.read(fname)
                    if len(data) != mf.get(size_key):
                        raise CalibrationPackageError(f"Größe für {fname} stimmt nicht überein")

                    sha256 = hashlib.sha256(data).hexdigest()
                    if sha256 != mf.get(hash_key):
                        raise CalibrationPackageError(f"Hash für {fname} stimmt nicht überein")

    except zipfile.BadZipFile:
        raise CalibrationPackageError("Kein gültiges ZIP-Archiv")