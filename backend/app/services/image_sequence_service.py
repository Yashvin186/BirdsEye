"""
Import a FOLDER OF FRAMES (e.g. Tanks and Temples, or frames exported from a video) instead of a video file.

The app runs on the user's own machine, so a multi-GB folder is read in place from its path - nothing is uploaded.
The frames are sorted naturally, evenly thinned to a cap (reconstruction time grows quickly with image count) and
written, at native resolution, into the project's source video. The marker file input/image_sequence.json tells the
frame extractor to use EVERY imported frame (no further temporal sub-sampling).
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
MAX_SIDE = 1920


def _natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def _dms(v, ref):
    d = float(v[0]) + float(v[1]) / 60.0 + float(v[2]) / 3600.0
    return -d if ref in ("S", "W") else d


def read_exif_gps(path: Path):
    """(lat, lon, alt) from a photo's EXIF GPS tags, or None."""
    try:
        from PIL import Image
        ex = Image.open(path)._getexif() or {}
        g = ex.get(34853)
        if not g or 2 not in g or 4 not in g:
            return None
        lat, lon = _dms(g[2], g.get(1, "N")), _dms(g[4], g.get(3, "E"))
        alt = float(g[6]) if 6 in g else 0.0
        if abs(lat) < 1e-6 and abs(lon) < 1e-6:
            return None
        return lat, lon, alt
    except Exception:
        return None


def _stamp(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


class ImageSequenceService:
    @staticmethod
    def find_images(folder: Path) -> List[Path]:
        """Images directly in `folder`; if none, the sub-folder (any depth) holding the most images."""
        folder = Path(folder).expanduser()
        if not folder.is_dir():
            raise ValueError(f"Folder not found: {folder}")
        direct = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT]
        if len(direct) >= 3:
            return sorted(direct, key=_natural_key)
        best: List[Path] = []
        for d in folder.rglob("*"):
            if d.is_dir():
                imgs = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT]
                if len(imgs) > len(best):
                    best = imgs
        if len(best) < 3:
            raise ValueError("No folder with at least 3 images (jpg/png) was found there.")
        return sorted(best, key=_natural_key)

    @classmethod
    def import_folder(cls, project_dir: Path, folder: str, max_images: int = 200, ffmpeg: str = "ffmpeg") -> Dict:
        imgs = cls.find_images(Path(folder))
        total = len(imgs)
        max_images = max(10, int(max_images))
        if total > max_images:
            idx = np.unique(np.linspace(0, total - 1, max_images).round().astype(int))
            imgs = [imgs[i] for i in idx]
        first = cv2.imread(str(imgs[0]))
        if first is None:
            raise ValueError(f"Could not read image {imgs[0].name}")
        h0, w0 = first.shape[:2]
        sc = min(1.0, MAX_SIDE / max(h0, w0))
        W, H = int(round(w0 * sc / 2) * 2), int(round(h0 * sc / 2) * 2)

        input_dir = Path(project_dir) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="seq_")) / "seq.mp4"
        FPS = 10
        wrote = cls._encode_ffmpeg(imgs, tmp, W, H, FPS, ffmpeg) or cls._encode_cv2(imgs, tmp, W, H, FPS)
        if not wrote:
            raise ValueError("Could not assemble the images into a sequence.")
        (input_dir / "image_sequence.json").write_text(json.dumps({
            "source_folder": str(folder), "images_found": total, "images_used": len(imgs), "fps": FPS,
            "first": imgs[0].name, "last": imgs[-1].name, "size": [W, H]}, indent=2), encoding="utf-8")
        # Photos from drones/phones often carry GPS in EXIF -> write a telemetry file so the model gets real-metre scale
        gps = [read_exif_gps(p) for p in imgs]
        have = sum(g is not None for g in gps)
        gps_used = False
        if have >= max(6, int(0.8 * len(imgs))):
            last = next(g for g in gps if g)
            blocks, prev = [], last
            for i, g in enumerate(gps):
                g = g or prev
                prev = g
                blocks.append(f"{i + 1}\n{_stamp(i / FPS)} --> {_stamp((i + 1) / FPS)}\n[latitude: {g[0]:.8f}] [longitude: {g[1]:.8f}] [rel_alt: {g[2]:.2f}]\n")
            (input_dir / "telemetry.srt").write_text("\n".join(blocks), encoding="utf-8")
            gps_used = True
        else:
            (input_dir / "telemetry.srt").unlink(missing_ok=True)
        return {"tmp_video": tmp, "exif_gps": gps_used, "images_with_gps": have, "images_found": total, "images_used": len(imgs), "size": [W, H]}

    @staticmethod
    def _encode_ffmpeg(imgs, out: Path, W, H, fps, ffmpeg) -> bool:
        try:
            lst = out.parent / "list.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\nduration {1.0 / fps}\n" for p in imgs), encoding="utf-8")
            cmd = [ffmpeg, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                   "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p", "-r", str(fps),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", str(out)]
            r = subprocess.run(cmd, capture_output=True, timeout=3600)
            return r.returncode == 0 and out.exists() and out.stat().st_size > 0
        except Exception:
            return False

    @staticmethod
    def _encode_cv2(imgs, out: Path, W, H, fps) -> bool:
        vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        if not vw.isOpened():
            return False
        for p in imgs:
            im = cv2.imread(str(p))
            if im is None:
                continue
            vw.write(cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA))
        vw.release()
        return out.exists() and out.stat().st_size > 0
