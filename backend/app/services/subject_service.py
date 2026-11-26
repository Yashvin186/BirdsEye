"""
Subject isolation: keep only the part of a dense cloud that structure-from-motion actually verified.

Why this exists
---------------
Dense stereo/MVS happily "reconstructs" everything the camera can see, including mountains, sky
and a river hundreds of metres away. With a short baseline those far points have depth errors as
large as the subject itself, so they come out as huge stretched sheets. They dominate the point
count (in the bundled test clip ~70% of dense points were background at 5-10x the subject's
distance), wreck the viewer framing, and make every mesher wrap the whole scene in giant triangles.

SfM's sparse points are different: each one was triangulated from several views with low
reprojection error. The region they occupy is where the geometry can be trusted. This service
builds an oriented box around that region (plus a margin) and drops dense points outside it.
"""
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import plyfile


class SubjectService:
    DEFAULT_MARGIN = 0.15          # fraction of the trusted extent added on every side
    PERCENTILES = (2.0, 98.0)      # robust extent of the sparse points (ignores stray tracks)
    MIN_TRUST_POINTS = 50          # fewer verified sparse points than this -> do not crop
    MIN_KEEP_FRACTION = 0.02       # cropping away >98% means sparse/dense disagree -> do not crop

    # ------------------------------------------------------------------ sparse points
    @staticmethod
    def read_sparse_points(model_dir: Path, max_error: float = 1.0, min_track: int = 3) -> np.ndarray:
        """Well-triangulated 3D points (N,3) from a COLMAP *text* model's points3D.txt."""
        points_txt = Path(model_dir) / "points3D.txt"
        if not points_txt.exists():
            return np.empty((0, 3), dtype=np.float64)
        pts = []
        with open(points_txt, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line or line.startswith("#"):
                    continue
                p = line.split()
                # POINT3D_ID X Y Z R G B ERROR (IMAGE_ID POINT2D_IDX)*
                if len(p) < 8:
                    continue
                try:
                    err = float(p[7])
                    track = (len(p) - 8) // 2
                    if err <= max_error and track >= min_track:
                        pts.append((float(p[1]), float(p[2]), float(p[3])))
                except ValueError:
                    continue
        return np.asarray(pts, dtype=np.float64) if pts else np.empty((0, 3), dtype=np.float64)

    # ------------------------------------------------------------------ trust volume
    @classmethod
    def build_trust_volume(
        cls,
        trust_points: np.ndarray,
        margin: float = DEFAULT_MARGIN,
    ) -> Optional[Dict[str, Any]]:
        """Oriented bounding box (PCA axes) around the robust core of the verified sparse points."""
        pts = np.asarray(trust_points, dtype=np.float64)
        pts = pts[np.all(np.isfinite(pts), axis=1)]
        if len(pts) < cls.MIN_TRUST_POINTS:
            return None

        # Ignore stray far-away tracks when choosing the axes.
        med = np.median(pts, axis=0)
        dist = np.linalg.norm(pts - med, axis=1)
        core = pts[dist <= np.percentile(dist, 90)]
        mu = core.mean(axis=0)
        _, _, vt = np.linalg.svd(core - mu, full_matrices=False)

        q = (pts - mu) @ vt.T
        lo, hi = np.percentile(q, cls.PERCENTILES, axis=0)
        ext = hi - lo
        # Flat scenes (e.g. a plain nadir pass) have almost no extent on the 3rd axis: give it a
        # sensible thickness so real relief above/below the plane is not clipped.
        pad = np.maximum(ext, 0.25 * ext.max()) * margin
        lo = lo - pad - np.maximum(0.0, 0.25 * ext.max() - ext) / 2.0
        hi = hi + pad + np.maximum(0.0, 0.25 * ext.max() - ext) / 2.0
        return {"mu": mu, "axes": vt, "lo": lo, "hi": hi, "n_trust_points": int(len(pts))}

    @staticmethod
    def inside(volume: Dict[str, Any], points: np.ndarray) -> np.ndarray:
        q = (np.asarray(points, dtype=np.float64) - volume["mu"]) @ volume["axes"].T
        return np.all((q >= volume["lo"]) & (q <= volume["hi"]), axis=1)

    # ------------------------------------------------------------------ PLY wrapper
    @classmethod
    def isolate_ply(
        cls,
        input_ply: Path,
        output_ply: Path,
        model_dir: Path,
        margin: float = DEFAULT_MARGIN,
        log_callback=None,
    ) -> Dict[str, Any]:
        """
        Write a copy of input_ply containing only points inside the SfM-verified volume.
        The input file is never modified. If the crop cannot be trusted it is skipped and the
        result says why (applied=False); the caller then keeps using the uncropped cloud.
        """
        ply = plyfile.PlyData.read(str(input_ply))
        vertex = ply["vertex"]
        xyz = np.column_stack([vertex["x"], vertex["y"], vertex["z"]]).astype(np.float64)
        total = len(xyz)

        def skipped(reason: str) -> Dict[str, Any]:
            if log_callback:
                log_callback(f"[NOTICE] Subject isolation skipped: {reason}")
            return {"applied": False, "reason": reason, "total_points": total, "kept_points": total,
                    "removed_points": 0, "output_ply": str(input_ply)}

        trust = cls.read_sparse_points(model_dir)
        volume = cls.build_trust_volume(trust, margin=margin)
        if volume is None:
            return skipped(f"only {len(trust)} verified sparse points available (need {cls.MIN_TRUST_POINTS}).")

        finite = np.all(np.isfinite(xyz), axis=1)
        keep = finite & cls.inside(volume, xyz)
        kept = int(keep.sum())
        if kept < 100 or kept / max(total, 1) < cls.MIN_KEEP_FRACTION:
            return skipped(f"crop would keep only {kept:,}/{total:,} points; sparse and dense clouds disagree.")

        out_vertex = plyfile.PlyElement.describe(vertex.data[keep], "vertex")
        others = [el for el in ply.elements if el.name != "vertex"]
        output_ply.parent.mkdir(parents=True, exist_ok=True)
        plyfile.PlyData([out_vertex] + others, text=ply.text).write(str(output_ply))

        extent = (volume["hi"] - volume["lo"]).tolist()
        if log_callback:
            log_callback(
                f"Subject isolation: kept {kept:,}/{total:,} dense points "
                f"({kept / total * 100:.1f}%) inside the SfM-verified volume "
                f"({volume['n_trust_points']:,} trusted sparse points, extent "
                f"{extent[0]:.1f} x {extent[1]:.1f} x {extent[2]:.1f}). "
                f"Removed {total - kept:,} far-field points (distant terrain, sky, unreliable depth)."
            )
        return {
            "applied": True,
            "reason": None,
            "total_points": total,
            "kept_points": kept,
            "removed_points": total - kept,
            "kept_fraction": kept / total,
            "trusted_sparse_points": volume["n_trust_points"],
            "volume_extent": extent,
            "output_ply": str(output_ply),
        }
