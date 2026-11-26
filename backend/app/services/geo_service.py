"""
Georeferencing from drone telemetry.

Consumer drones (DJI etc.) write a sidecar subtitle file (.SRT) next to every video with GPS + altitude per frame.
We use it to turn the arbitrary-scale SfM model into REAL METRES:

  1. parse the SRT -> (time, lat, lon, altitude) samples,
  2. interpolate the GPS position at each extracted frame's timestamp,
  3. convert to a local East-North-Up frame in metres,
  4. robustly fit a similarity transform (scale + rotation + translation, Umeyama + RANSAC) that maps the SfM camera
     centres onto the GPS positions,
  5. report metres-per-unit, the compass orientation and the residual (RMSE) so the accuracy is stated honestly.

Honest limits: consumer GPS is good to a few metres, so absolute position is only that good and altitude is worse.
SCALE is what we gain - it is averaged over the whole flight path, so it is far more accurate than a single GPS fix.
"""
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
_LAT = re.compile(r"lat(?:itude)?\s*[:=]\s*(-?\d+\.\d+)", re.I)
_LON = re.compile(r"lon(?:gitude)?\s*[:=]\s*(-?\d+\.\d+)", re.I)
_REL = re.compile(r"rel_alt\s*[:=]\s*(-?\d+(?:\.\d+)?)", re.I)
_ABS = re.compile(r"(?:abs_alt|altitude|alt)\s*[:=]\s*(-?\d+(?:\.\d+)?)", re.I)
_GPS_OLD = re.compile(r"GPS\s*\(\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)", re.I)  # lon, lat, alt


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / (10 ** len(ms))


class GeoService:
    MIN_CAMERAS = 6

    # ------------------------------------------------------------------ parsing
    @staticmethod
    def parse_srt(path: Path) -> List[Dict[str, float]]:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        samples: List[Dict[str, float]] = []
        for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
            tm = _TIME.search(block)
            if not tm:
                continue
            t0 = _secs(*tm.groups()[:4])
            t1 = _secs(*tm.groups()[4:])
            lat = _LAT.search(block)
            lon = _LON.search(block)
            alt = None
            if lat and lon:
                lat_v, lon_v = float(lat.group(1)), float(lon.group(1))
            else:
                old = _GPS_OLD.search(block)
                if not old:
                    continue
                lon_v, lat_v, alt = float(old.group(1)), float(old.group(2)), float(old.group(3))
            rel = _REL.search(block)
            ab = _ABS.search(block)
            if rel:
                alt = float(rel.group(1))
            elif ab:
                alt = float(ab.group(1))
            if alt is None:
                alt = 0.0
            samples.append({"t": t0, "lat": lat_v, "lon": lon_v, "alt": alt})
        return samples

    @staticmethod
    def interpolate(samples: List[Dict[str, float]], t: float) -> Optional[Dict[str, float]]:
        if not samples:
            return None
        ts = np.array([s["t"] for s in samples])
        if t < ts[0] - 1.0 or t > ts[-1] + 1.0:
            return None
        return {k: float(np.interp(t, ts, [s[k] for s in samples])) for k in ("lat", "lon", "alt")}

    @staticmethod
    def to_enu(lat, lon, alt, lat0, lon0, alt0) -> np.ndarray:
        phi = math.radians(lat0)
        m_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
        m_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
        return np.column_stack([(np.asarray(lon) - lon0) * m_lon, (np.asarray(lat) - lat0) * m_lat, np.asarray(alt) - alt0])

    # ------------------------------------------------------------------ similarity fit
    @staticmethod
    def umeyama(src: np.ndarray, dst: np.ndarray):
        mu_s, mu_d = src.mean(0), dst.mean(0)
        xs, xd = src - mu_s, dst - mu_d
        cov = xd.T @ xs / len(src)
        U, S, Vt = np.linalg.svd(cov)
        D = np.eye(3)
        if np.linalg.det(U) * np.linalg.det(Vt) < 0:
            D[2, 2] = -1
        R = U @ D @ Vt
        var = (xs ** 2).sum() / len(src)
        s = float(np.trace(np.diag(S) @ D) / max(var, 1e-12))
        t = mu_d - s * R @ mu_s
        return s, R, t

    @classmethod
    def robust_similarity(cls, src: np.ndarray, dst: np.ndarray, iters: int = 300, seed: int = 0):
        rng = np.random.default_rng(seed)
        n = len(src)
        s, R, t = cls.umeyama(src, dst)
        err = np.linalg.norm((s * (src @ R.T) + t) - dst, axis=1)
        thr = max(3.0 * float(np.median(err)) * 1.4826, 2.0)       # metres; consumer GPS noise is a few metres
        best = err < thr
        for _ in range(iters):
            idx = rng.choice(n, 4, replace=False)
            try:
                s_, R_, t_ = cls.umeyama(src[idx], dst[idx])
            except Exception:
                continue
            e = np.linalg.norm((s_ * (src @ R_.T) + t_) - dst, axis=1)
            inl = e < thr
            if inl.sum() > best.sum():
                best = inl
        s, R, t = cls.umeyama(src[best], dst[best])
        err = np.linalg.norm((s * (src @ R.T) + t) - dst, axis=1)
        return s, R, t, best, err

    # ------------------------------------------------------------------ main entry
    @classmethod
    def georeference(cls, project_dir: Path, model_dir: Path, log=None) -> Dict[str, Any]:
        """Returns a result dict; status is 'gps_aligned' or a reason it could not be done (never raises)."""
        log = log or (lambda s: None)
        project_dir = Path(project_dir)
        srt = None
        for cand in sorted((project_dir / "input").glob("*")):
            if cand.suffix.lower() in (".srt", ".gpslog") or cand.name.lower().startswith("telemetry"):
                srt = cand
                break
        if srt is None:
            return {"status": "no_telemetry", "reason": "No drone telemetry (.SRT) file was provided, so scale is relative."}
        try:
            samples = cls.parse_srt(srt)
        except Exception as exc:
            return {"status": "telemetry_unreadable", "reason": f"Could not read {srt.name}: {exc}"}
        if len(samples) < 3:
            return {"status": "telemetry_unreadable", "reason": f"{srt.name} contains no usable GPS samples."}

        from app.services.cpu_dense_service import CpuDenseService
        _cams, images = CpuDenseService.read_text_model(Path(model_dir))
        manifest = json.loads((project_dir / "frames" / "frame_manifest.json").read_text(encoding="utf-8"))
        ts = {r["filename"]: r["timestamp_sec"] for r in manifest["records"] if r.get("accepted") and r.get("filename")}

        centres, gps = [], []
        for im in images:
            t = ts.get(im["name"])
            if t is None:
                continue
            g = cls.interpolate(samples, t)
            if g is None:
                continue
            centres.append(im["C"])
            gps.append([g["lat"], g["lon"], g["alt"]])
        if len(centres) < cls.MIN_CAMERAS:
            return {"status": "insufficient_overlap", "reason": f"Only {len(centres)} registered frames could be matched to GPS samples."}
        centres, gps = np.array(centres), np.array(gps)
        lat0, lon0, alt0 = float(np.mean(gps[:, 0])), float(np.mean(gps[:, 1])), float(np.mean(gps[:, 2]))
        enu = cls.to_enu(gps[:, 0], gps[:, 1], gps[:, 2], lat0, lon0, alt0)
        extent = float(np.linalg.norm(enu - enu.mean(0), axis=1).max())
        if extent < 3.0:
            return {"status": "insufficient_motion", "reason": f"The drone moved only {extent:.1f} m according to GPS - too little to fix the scale."}

        s, R, t, inl, err = cls.robust_similarity(centres, enu)
        rmse = float(np.sqrt(np.mean(err[inl] ** 2)))
        if not (np.isfinite(s) and s > 0):
            return {"status": "alignment_failed", "reason": "GPS and camera path could not be aligned."}
        # Direction of ENU north expressed in SfM coordinates (for orienting the model north-up)
        north_sfm = R.T @ np.array([0.0, 1.0, 0.0])
        east_sfm = R.T @ np.array([1.0, 0.0, 0.0])
        up_sfm = R.T @ np.array([0.0, 0.0, 1.0])
        result = {
            "status": "gps_aligned", "source": srt.name,
            "metres_per_unit": s, "rmse_m": rmse, "inlier_cameras": int(inl.sum()), "cameras_used": int(len(centres)),
            "path_extent_m": extent, "origin": {"lat": lat0, "lon": lon0, "alt": alt0},
            "rotation": R.tolist(), "translation": t.tolist(),
            "east_sfm": east_sfm.tolist(), "north_sfm": north_sfm.tolist(), "up_sfm": up_sfm.tolist(),
        }
        (project_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (project_dir / "outputs" / "georeference.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        log(f"Georeferenced from {srt.name}: 1 model unit = {s:.4f} m, RMSE {rmse:.1f} m over {int(inl.sum())}/{len(centres)} frames.")
        return result
