"""
Post-flight capture QA (run BEFORE the expensive reconstruction).

Photogrammetry guides (MUGIN, UAVCoach) agree that most failed models are decided at capture time:
too little overlap, blur, abrupt turns / cuts, or too few frames. We measure those from the extracted frames
and give a verdict plus plain advice, so the user does not wait for a long run on footage that cannot work.

Metrics (all measured, none guessed):
  * sharpness   - variance of Laplacian per frame (from the manifest); share of frames below 50 % of the median
  * overlap     - between consecutive selected frames: ORB matches filtered by a RANSAC fundamental matrix;
                  overlap % = area of the convex hull of inlier points in frame A / frame area
                  (a proxy for forward overlap; guides ask for >75 %)
  * breaks      - consecutive pairs with too few inliers (tracking breaks: cuts, fast turns, blur)
  * telemetry   - fraction of frame timestamps covered by the .SRT (enables metric scale)
"""
import json
from pathlib import Path
from typing import Any, Dict

import cv2
import numpy as np

from app.services.geo_service import GeoService

# The proxy (hull of matched features) under-reads true image overlap, so its thresholds are lower than the
# 75 % guideline. Calibrated on our runs: the synthetic orbit (34 %) and the real survey reconstructed fine.
OVERLAP_GOOD = 50.0
OVERLAP_MIN = 30.0
MIN_FRAMES = 12


class CaptureQAService:
    @staticmethod
    def _pair_overlap(a: np.ndarray, b: np.ndarray, orb) -> Dict[str, float]:
        ka, da = orb.detectAndCompute(a, None)
        kb, db = orb.detectAndCompute(b, None)
        if da is None or db is None or len(ka) < 12 or len(kb) < 12:
            return {"inliers": 0, "overlap": 0.0}
        m = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
        good = [x[0] for x in m if len(x) == 2 and x[0].distance < 0.8 * x[1].distance]
        if len(good) < 12:
            return {"inliers": len(good), "overlap": 0.0}
        pa = np.float32([ka[g.queryIdx].pt for g in good])
        pb = np.float32([kb[g.trainIdx].pt for g in good])
        F, mask = cv2.findFundamentalMat(pa, pb, cv2.FM_RANSAC, 1.5, 0.99)
        if F is None or mask is None:
            return {"inliers": 0, "overlap": 0.0}
        inl = mask.ravel().astype(bool)
        n = int(inl.sum())
        if n < 8:
            return {"inliers": n, "overlap": 0.0}
        hull = cv2.convexHull(pa[inl])
        area = float(cv2.contourArea(hull)) / float(a.shape[0] * a.shape[1])
        return {"inliers": n, "overlap": min(100.0, 100.0 * area)}

    @classmethod
    def analyze(cls, project_dir: Path, frames_res: Dict[str, Any], log=None) -> Dict[str, Any]:
        log = log or (lambda s: None)
        project_dir = Path(project_dir)
        try:
            manifest = json.loads((project_dir / "frames" / "frame_manifest.json").read_text(encoding="utf-8"))
            recs = [r for r in manifest["records"] if r.get("accepted") and r.get("filename")]
        except Exception as exc:
            return {"available": False, "reason": f"manifest unreadable: {exc}"}
        n = len(recs)
        issues, advice = [], []

        sharp = np.array([r.get("sharpness", 0.0) for r in recs], dtype=float)
        med = float(np.median(sharp)) if n else 0.0
        blurry = int((sharp < 0.5 * med).sum()) if n and med > 0 else 0
        blur_pct = 100.0 * blurry / max(n, 1)

        # overlap between consecutive selected frames
        orb = cv2.ORB_create(1500)
        overlaps, inl_counts = [], []
        prev = None
        for r in recs:
            img = cv2.imread(str(project_dir / "frames" / r["filename"]), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            scale = 640.0 / max(img.shape)
            if scale < 1:
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            if prev is not None:
                p = cls._pair_overlap(prev, img, orb)
                overlaps.append(p["overlap"])
                inl_counts.append(p["inliers"])
            prev = img
        ov = np.array(overlaps) if overlaps else np.zeros(0)
        breaks = int(((np.array(inl_counts) < 15).sum())) if inl_counts else 0
        ov_med = float(np.median(ov)) if len(ov) else 0.0
        ov_p10 = float(np.percentile(ov, 10)) if len(ov) else 0.0

        # telemetry coverage
        tel = {"present": False}
        srt = next((c for c in sorted((project_dir / "input").glob("*"))
                    if c.suffix.lower() in (".srt", ".gpslog") or c.name.lower().startswith("telemetry")), None)
        if srt is not None:
            try:
                samples = GeoService.parse_srt(srt)
                cov = sum(1 for r in recs if GeoService.interpolate(samples, r["timestamp_sec"]) is not None)
                tel = {"present": True, "samples": len(samples), "frame_coverage_percent": round(100.0 * cov / max(n, 1), 1)}
            except Exception:
                tel = {"present": True, "samples": 0, "frame_coverage_percent": 0.0}

        score_bad = 0
        if n < MIN_FRAMES:
            issues.append(f"Only {n} usable frames were selected (need at least {MIN_FRAMES}).")
            advice.append("Use a longer clip or lower the frame step so more frames are kept.")
            score_bad += 2
        if len(ov) and ov_med < OVERLAP_MIN:
            issues.append(f"Median forward overlap is about {ov_med:.0f} % (feature-hull proxy; aim for >75 % true overlap, proxy ~{OVERLAP_GOOD:.0f} %+).")
            advice.append("Fly slower or extract frames more often; keep consecutive views overlapping by at least 75 %.")
            score_bad += 2
        elif len(ov) and ov_med < OVERLAP_GOOD:
            issues.append(f"Forward overlap is about {ov_med:.0f} %, below the proxy target of {OVERLAP_GOOD:.0f} %.")
            advice.append("A slightly slower pass or denser frame selection would make the model more robust.")
            score_bad += 1
        if breaks:
            issues.append(f"{breaks} tracking break(s): consecutive frames share too few features (cuts, fast turns or blur).")
            advice.append("Reconstruction needs ONE continuous camera path. Avoid cuts, fades and sharp turns; re-fly the broken section.")
            score_bad += 2 if breaks > max(1, 0.1 * n) else 1
        if blur_pct > 25:
            issues.append(f"{blur_pct:.0f} % of frames are noticeably blurry.")
            advice.append("Use a faster shutter / lower speed; blurred video frames are the main cause of soft textures.")
            score_bad += 1
        if not tel["present"]:
            advice.append("Add the drone's .SRT file to get real-world scale (metres) and north-up orientation.")

        verdict = "good" if score_bad == 0 else ("marginal" if score_bad <= 2 else "poor")
        result = {
            "available": True, "verdict": verdict, "frames": n,
            "overlap_median_percent": round(ov_med, 1), "overlap_p10_percent": round(ov_p10, 1),
            "tracking_breaks": breaks, "blurry_frames_percent": round(blur_pct, 1),
            "telemetry": tel, "issues": issues, "advice": advice,
            "reference_thresholds": {"overlap_recommended_percent": 75, "proxy_target_percent": OVERLAP_GOOD,
                                     "source": "MUGIN / UAVCoach photogrammetry capture guidance"},
            "note": "Overlap is estimated from feature matches between consecutive selected frames; it is a proxy, not a flight-log value.",
        }
        (project_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (project_dir / "outputs" / "capture_qa.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        log(f"Capture QA: {verdict} - overlap ~{ov_med:.0f}%, {breaks} break(s), {blur_pct:.0f}% blurry frames.")
        for i in issues:
            log("  ! " + i)
        return result
