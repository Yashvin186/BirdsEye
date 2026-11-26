"""
Viewpoint coverage: how far around the subject did the camera actually go?

A 3D model can only contain surfaces that at least two frames saw. A single forward pass sees one side
(like a relief); a full orbit sees all sides. This service measures that directly from the solved camera
poses so the user is told, before and after reconstruction, whether a complete 360-degree model is
possible from this video, and which directions are missing.
"""
from pathlib import Path
from typing import Any, Dict

import numpy as np

from app.services.cpu_dense_service import CpuDenseService
from app.services.subject_service import SubjectService


class CoverageService:
    BINS = 12                      # 30-degree sectors
    FULL_ORBIT_DEG = 300.0         # span needed to call the capture a full orbit
    PARTIAL_DEG = 120.0

    @classmethod
    def analyze(cls, model_dir: Path) -> Dict[str, Any]:
        model_dir = Path(model_dir)
        try:
            cams, images = CpuDenseService.read_text_model(model_dir)
        except Exception as exc:
            return {"available": False, "reason": f"camera poses unreadable: {exc}"}

        centres, downs = [], []
        for im in images:
            centres.append(im["C"])
            downs.append(im["R"].T @ np.array([0.0, 1.0, 0.0]))   # camera "down" in world coordinates
        centres = np.asarray(centres)
        if len(centres) < 3:
            return {"available": False, "reason": "fewer than 3 registered cameras"}

        trust = SubjectService.read_sparse_points(model_dir)
        subject = np.median(trust, axis=0) if len(trust) >= 20 else centres.mean(axis=0)

        down = np.mean(downs, axis=0)
        down /= max(np.linalg.norm(down), 1e-9)
        up = -down
        # Basis of the horizontal plane (perpendicular to up).
        a = np.cross(up, [1.0, 0.0, 0.0])
        if np.linalg.norm(a) < 1e-3:
            a = np.cross(up, [0.0, 0.0, 1.0])
        a /= np.linalg.norm(a)
        b = np.cross(up, a)

        rel = centres - subject
        horiz = np.column_stack([rel @ a, rel @ b])
        radius = np.linalg.norm(horiz, axis=1)
        ok = radius > 1e-6
        if ok.sum() < 3:
            return {"available": False, "reason": "cameras are directly above the subject"}
        ang = np.degrees(np.arctan2(horiz[ok, 1], horiz[ok, 0])) % 360.0

        # Largest empty gap between neighbouring viewing directions -> angular span actually covered.
        srt = np.sort(ang)
        gaps = np.diff(np.concatenate([srt, [srt[0] + 360.0]]))
        span = float(360.0 - gaps.max())
        bins = np.zeros(cls.BINS, dtype=int)
        for x in ang:
            bins[int(x // (360.0 / cls.BINS)) % cls.BINS] += 1
        covered = int((bins > 0).sum())
        elev = np.degrees(np.arctan2(rel[ok] @ up, radius[ok]))

        if span >= cls.FULL_ORBIT_DEG:
            verdict, level = "full_orbit", "good"
            message = "The camera went (almost) all the way around the subject, so a complete 3D model is possible."
        elif span >= cls.PARTIAL_DEG:
            verdict, level = "partial_orbit", "warning"
            message = (f"The camera covered about {span:.0f} degrees around the subject. Surfaces facing the other "
                       f"{360 - span:.0f} degrees were never filmed and cannot appear in the model.")
        else:
            verdict, level = "single_side", "limited"
            message = (f"The camera moved through only about {span:.0f} degrees, so only ONE side of the subject was filmed. "
                       "The result is a front-facing relief, not a complete object. For a full 3D model, film a slow orbit "
                       "around it (a circle, camera aimed at the subject, ~45 degrees down) plus a second, lower circle.")
        # Where is the biggest hole? (direction from the subject, in model coordinates) -> capture planner
        gi = int(np.argmax(gaps))
        mid = np.radians(srt[gi] + gaps[gi] / 2.0)
        gap_dir = np.cos(mid) * a + np.sin(mid) * b
        return {
            "gap_deg": round(float(gaps.max()), 1),
            "gap_mid_dir_sfm": gap_dir.tolist(),
            "available": True,
            "verdict": verdict,
            "level": level,
            "message": message,
            "angular_span_deg": round(span, 1),
            "sectors_covered": covered,
            "sectors_total": cls.BINS,
            "coverage_percent": round(100.0 * covered / cls.BINS, 1),
            "sector_counts": bins.tolist(),
            "mean_elevation_deg": round(float(np.mean(elev)), 1),
            "cameras": int(len(centres)),
        }
