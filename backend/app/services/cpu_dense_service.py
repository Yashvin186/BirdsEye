"""
CPU dense reconstruction fallback (OpenCV semi-global stereo + multi-view consistency).

COLMAP's dense stage (patch_match_stereo) needs CUDA. Without it the app used to stop at the
sparse SfM cloud (a few thousand points) and could not produce a model. This service builds a
dense, coloured cloud on any machine from the camera poses SfM already solved:

  1. choose image pairs with a baseline that suits the scene depth,
  2. rectify each pair and run semi-global block matching,
  3. back-project the disparities into the SfM world frame,
  4. keep only points that two or more *different* pairs agree on (voxel consistency), which
     removes most single-pair stereo noise.

It is deliberately honest about its limits: it needs a camera that actually translates (pure
rotation / hovering gives no depth), and it is a classical stereo method, so it is noisier than
CUDA MVS on texture-poor surfaces.
"""
import math
from app.core.presets import get_preset
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import plyfile

from app.services.subject_service import SubjectService


class CpuDenseService:
    MAX_DIM = 1600              # longest image side used for matching (speed/memory)
    MAX_PAIRS = 40
    BASELINE_SCALES = (0.7, 1.5)    # baselines tried per frame, as multiples of the target baseline
    TARGET_BASELINE_RATIO = 0.035   # baseline / typical scene depth that gives usable disparity
    MIN_VOXEL_VIEWS = 2             # a voxel must be supported by this many distinct pairs
    VOXEL_PIXELS = 4.0              # consistency voxel size, in pixels at the typical scene depth
    MAX_AXIS_ANGLE_DEG = 25.0       # max angle between the two cameras' viewing directions
    MAX_FORWARD_FRACTION = 0.7      # skip pairs whose motion is mostly along the viewing axis
    MIN_TEXTURE = 6.0               # mean |horizontal gradient| (0-255 scale, 9x9 window) needed to trust a match
    MIN_TEXTURE_KEEP_FRACTION = 0.15  # never let the gate remove more than 85% of a pair's matches

    # ------------------------------------------------------------------ model parsing
    @staticmethod
    def _quat_to_rot(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
        n = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz) or 1.0
        qw, qx, qy, qz = qw / n, qx / n, qy / n, qz / n
        return np.array([
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
        ])

    @classmethod
    def _camera_from_params(cls, model: str, w: int, h: int, p: List[float]) -> Tuple[np.ndarray, np.ndarray]:
        """(3x3 K, distortion) in OpenCV convention for the COLMAP camera models we can rectify."""
        if model == "SIMPLE_PINHOLE":
            f, cx, cy = p; fx = fy = f; d = [0, 0, 0, 0]
        elif model == "PINHOLE":
            fx, fy, cx, cy = p; d = [0, 0, 0, 0]
        elif model == "SIMPLE_RADIAL":
            f, cx, cy, k = p; fx = fy = f; d = [k, 0, 0, 0]
        elif model == "RADIAL":
            f, cx, cy, k1, k2 = p; fx = fy = f; d = [k1, k2, 0, 0]
        elif model == "OPENCV":
            fx, fy, cx, cy, k1, k2, p1, p2 = p; d = [k1, k2, p1, p2]
        else:
            raise ValueError(
                f"Camera model {model} is not supported by the CPU stereo fallback "
                "(supported: SIMPLE_PINHOLE, PINHOLE, SIMPLE_RADIAL, RADIAL, OPENCV)."
            )
        K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
        return K, np.array(d, dtype=np.float64)

    @classmethod
    def read_text_model(cls, model_dir: Path) -> Tuple[Dict[int, Dict[str, Any]], List[Dict[str, Any]]]:
        cams: Dict[int, Dict[str, Any]] = {}
        with open(Path(model_dir) / "cameras.txt", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip() or line.startswith("#"):
                    continue
                t = line.split()
                cid, model, w, h = int(t[0]), t[1], int(t[2]), int(t[3])
                K, D = cls._camera_from_params(model, w, h, [float(x) for x in t[4:]])
                cams[cid] = {"K": K, "D": D, "w": w, "h": h}

        images: List[Dict[str, Any]] = []
        with open(Path(model_dir) / "images.txt", "r", encoding="utf-8", errors="ignore") as f:
            lines = [ln for ln in f if not ln.startswith("#")]
        # images.txt alternates: pose line, then a (possibly empty) 2D-points line.
        for i in range(0, len(lines) - 1, 2):
            t = lines[i].split()
            if len(t) < 10:
                continue
            qw, qx, qy, qz, tx, ty, tz = (float(v) for v in t[1:8])
            R = cls._quat_to_rot(qw, qx, qy, qz)
            tvec = np.array([tx, ty, tz])
            images.append({
                "name": t[9], "camera_id": int(t[8]), "R": R, "t": tvec,
                "C": -R.T @ tvec,           # camera centre in world coordinates
            })
        return cams, images

    # ------------------------------------------------------------------ pair selection
    @classmethod
    def select_pairs(
        cls, images: List[Dict[str, Any]], ref_depth: float, max_pairs: int = MAX_PAIRS
    ) -> List[Tuple[int, int]]:
        """Pairs whose baseline is ~TARGET_BASELINE_RATIO of the scene depth and that look the same way."""
        target = cls.TARGET_BASELINE_RATIO * ref_depth
        cos_limit = math.cos(math.radians(cls.MAX_AXIS_ANGLE_DEG))
        n = len(images)
        fwd = np.array([im["R"][2] for im in images])      # camera z axis in world coordinates
        cen = np.array([im["C"] for im in images])

        def best_partner(i: int, lo: float, hi: float, scale: float = 1.0) -> Optional[int]:
            best, best_err = None, None
            for j in range(n):
                if j == i or float(fwd[i] @ fwd[j]) < cos_limit:
                    continue
                b = cen[j] - cen[i]
                bl = float(np.linalg.norm(b))
                if not (lo * target <= bl <= hi * target):
                    continue
                if abs(float(fwd[i] @ b)) / max(bl, 1e-12) > cls.MAX_FORWARD_FRACTION:
                    continue                                 # mostly forward motion: rectification degenerates
                err = abs(bl - target * scale)
                if best_err is None or err < best_err:
                    best, best_err = j, err
            return best

        for lo, hi in ((0.5, 2.0), (0.2, 5.0)):
            pairs, seen = [], set()
            # Two baselines per frame: a short one (robust matching) and a longer one (better depth),
            # which also gives the multi-pair consistency check more independent evidence.
            for scale in cls.BASELINE_SCALES:
                for i in range(n):
                    j = best_partner(i, lo, hi, scale)
                    if j is None:
                        continue
                    key = (min(i, j), max(i, j))
                    if key not in seen:
                        seen.add(key)
                        pairs.append((i, j))
            if pairs:
                if len(pairs) > max_pairs:
                    idx = np.linspace(0, len(pairs) - 1, max_pairs).round().astype(int)
                    pairs = [pairs[k] for k in sorted(set(idx.tolist()))]
                return pairs
        return []

    # ------------------------------------------------------------------ main entry
    @classmethod
    def run(
        cls,
        project_dir: Path,
        primary_sparse_model: Path,
        margin: float = SubjectService.DEFAULT_MARGIN,
        quality_preset: str = "balanced",
        log_callback=None,
    ) -> Dict[str, Any]:
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        def failed(reason: str) -> Dict[str, Any]:
            log(f"[ERROR] CPU stereo fallback failed: {reason}")
            return {"dense_ply": None, "dense_point_count": 0, "status": "failed", "reason": reason}

        frames_dir = Path(project_dir) / "frames"
        outputs_dir = Path(project_dir) / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        try:
            cams, images = cls.read_text_model(primary_sparse_model)
        except Exception as e:
            return failed(f"could not read the SfM model ({e}).")
        if len(images) < 2:
            return failed("fewer than 2 registered cameras.")

        trust = SubjectService.read_sparse_points(primary_sparse_model)
        if len(trust) < SubjectService.MIN_TRUST_POINTS:
            trust = SubjectService.read_sparse_points(primary_sparse_model, max_error=4.0, min_track=2)
        if len(trust) < 10:
            return failed("SfM produced too few verified 3D points to anchor a dense reconstruction.")

        # Depth of the verified points in every registered camera -> typical scene depth.
        depths = []
        for im in images:
            z = (trust @ im["R"].T + im["t"])[:, 2]
            depths.append(z[z > 0])
        all_depths = np.concatenate(depths) if depths else np.array([])
        if len(all_depths) == 0:
            return failed("verified 3D points are not in front of any camera.")
        ref_depth = float(np.median(all_depths))

        pairs = cls.select_pairs(images, ref_depth)
        if not pairs:
            return failed(
                "no image pair has a usable baseline. The camera barely moves (or only rotates), "
                "so there is no parallax to measure depth from. Fly sideways/forward while filming."
            )
        log(f"CPU stereo fallback: {len(images)} registered cameras, scene depth ~{ref_depth:.1f}, "
            f"{len(pairs)} stereo pairs selected (CUDA MVS unavailable).")

        volume = SubjectService.build_trust_volume(trust, margin=margin)
        first_cam = cams[images[0]["camera_id"]]
        scale = min(1.0, min(cls.MAX_DIM, get_preset(quality_preset).mvs_dim) / float(max(first_cam["w"], first_cam["h"])))
        voxel = cls.VOXEL_PIXELS * ref_depth / (float(first_cam["K"][0, 0]) * scale)
        origin = volume["mu"] if volume is not None else trust.mean(axis=0)

        bag_keys, bag_pos, bag_col, bag_cnt = [], [], [], []
        used_pairs = 0
        matched_total = 0       # stereo matches before cropping to the verified volume
        in_volume_total = 0     # ... and after

        for pid, (a, b) in enumerate(pairs):
            A, B = images[a], images[b]
            camA, camB = cams[A["camera_id"]], cams[B["camera_id"]]
            # Put the camera on the right of the pair second so disparities are positive.
            if float((A["R"] @ (B["C"] - A["C"]))[0]) < 0:
                A, B, camA, camB = B, A, camB, camA

            imgA = cv2.imread(str(frames_dir / A["name"]))
            imgB = cv2.imread(str(frames_dir / B["name"]))
            if imgA is None or imgB is None:
                log(f"[WARNING] pair {pid + 1}/{len(pairs)}: frame image missing on disk, skipped.")
                continue

            def prep(img, cam):
                # Resize to (camera size x scale) regardless of the stored frame's size, so the
                # intrinsics always match the pixels they describe.
                sz = (int(round(cam["w"] * scale)), int(round(cam["h"] * scale)))
                im = cv2.resize(img, sz, interpolation=cv2.INTER_AREA)
                K = cam["K"].copy(); K[:2] *= scale
                return im, K, sz

            imgA, KA, size = prep(imgA, camA)
            imgB, KB, _ = prep(imgB, camB)

            R = B["R"] @ A["R"].T
            T = B["t"] - R @ A["t"]
            try:
                R1r, R2r, P1, P2, Q, _, _ = cv2.stereoRectify(
                    KA, camA["D"], KB, camB["D"], size, R, T.reshape(3, 1),
                    flags=cv2.CALIB_ZERO_DISPARITY, alpha=0
                )
            except cv2.error as e:
                log(f"[WARNING] pair {pid + 1}/{len(pairs)}: rectification failed ({e}), skipped.")
                continue
            mapA = cv2.initUndistortRectifyMap(KA, camA["D"], R1r, P1, size, cv2.CV_32FC1)
            mapB = cv2.initUndistortRectifyMap(KB, camB["D"], R2r, P2, size, cv2.CV_32FC1)
            left = cv2.remap(imgA, *mapA, cv2.INTER_LINEAR)
            right = cv2.remap(imgB, *mapB, cv2.INTER_LINEAR)

            # Disparity search range from the nearest verified structure.
            baseline = float(np.linalg.norm(T))
            z_near = float(np.percentile(np.concatenate(depths), 2)) if len(all_depths) else ref_depth
            d_max = float(P1[0, 0]) * baseline / max(z_near, 1e-6)
            num_disp = int(min(320, max(32, math.ceil(d_max * 1.4 / 16.0) * 16)))

            bs = 5
            sgbm = cv2.StereoSGBM_create(
                minDisparity=0, numDisparities=num_disp, blockSize=bs,
                P1=8 * 3 * bs * bs, P2=32 * 3 * bs * bs,
                uniquenessRatio=8, speckleWindowSize=120, speckleRange=2, disp12MaxDiff=1,
                mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
            )
            disp = sgbm.compute(cv2.cvtColor(left, cv2.COLOR_BGR2GRAY),
                                cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)).astype(np.float32) / 16.0
            ok = np.isfinite(disp) & (disp > 1.5)
            if not ok.any():
                continue

            # Texture gate. Stereo cannot measure depth on featureless surfaces (water, sand, sky,
            # glare): semi-global matching just smooths a plausible-looking but wrong surface across
            # them, which later turns into blobs on the mesh. Matching works on horizontal intensity
            # changes, so require some of them around each pixel.
            if cls.MIN_TEXTURE > 0:
                gx = np.abs(cv2.Sobel(cv2.cvtColor(left, cv2.COLOR_BGR2GRAY), cv2.CV_32F, 1, 0, ksize=3))
                textured = cv2.blur(gx, (9, 9)) >= cls.MIN_TEXTURE
                gated = ok & textured
                # Safety: on a genuinely smooth scene do not throw the whole pair away.
                if gated.sum() >= cls.MIN_TEXTURE_KEEP_FRACTION * ok.sum():
                    ok = gated
                else:
                    log(f"[NOTICE] pair {pid + 1}/{len(pairs)}: very low texture, texture gate relaxed.")
            xyz = cv2.reprojectImageTo3D(disp, Q)
            P_rect = xyz[ok].astype(np.float64)
            col = left[ok][:, ::-1]                              # BGR -> RGB
            good_z = np.isfinite(P_rect).all(axis=1) & (P_rect[:, 2] > 0)
            P_rect, col = P_rect[good_z], col[good_z]
            if len(P_rect) == 0:
                continue
            # rectified-left frame -> original left camera frame -> world
            Xc = P_rect @ R1r
            Xw = (Xc - A["t"]) @ A["R"]

            matched_total += len(Xw)
            if volume is not None:                                # crop early: saves memory/time
                m = SubjectService.inside(volume, Xw)
                Xw, col = Xw[m], col[m]
            in_volume_total += len(Xw)
            if len(Xw) == 0:
                continue

            # Reduce this pair to one entry per voxel so cross-pair agreement can be counted.
            ijk = np.floor((Xw - origin) / voxel).astype(np.int64) + (1 << 20)
            if ijk.min() < 0 or ijk.max() >= (1 << 21):
                continue                                          # absurd coordinates: ignore pair
            key = (ijk[:, 0] << 42) | (ijk[:, 1] << 21) | ijk[:, 2]
            uniq, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
            pos_sum = np.stack([np.bincount(inv, weights=Xw[:, k]) for k in range(3)], axis=1)
            col_sum = np.stack([np.bincount(inv, weights=col[:, k].astype(np.float64)) for k in range(3)], axis=1)
            bag_keys.append(uniq); bag_pos.append(pos_sum); bag_col.append(col_sum); bag_cnt.append(cnt)
            used_pairs += 1
            log(f"CPU stereo pair {pid + 1}/{len(pairs)}: baseline {baseline:.2f}, {int(ok.sum()):,} matches, "
                f"{len(uniq):,} voxels in the verified volume.")

        if used_pairs == 0:
            return failed("no stereo pair produced usable depth.")

        keys = np.concatenate(bag_keys)
        pos = np.concatenate(bag_pos)
        col_s = np.concatenate(bag_col)
        cnt = np.concatenate(bag_cnt).astype(np.float64)
        uniq, inv, views = np.unique(keys, return_inverse=True, return_counts=True)   # views = #pairs per voxel
        total_cnt = np.bincount(inv, weights=cnt)
        pos_mean = np.stack([np.bincount(inv, weights=pos[:, k]) for k in range(3)], axis=1) / total_cnt[:, None]
        col_mean = np.stack([np.bincount(inv, weights=col_s[:, k]) for k in range(3)], axis=1) / total_cnt[:, None]

        total_voxels = len(uniq)
        keep = views >= cls.MIN_VOXEL_VIEWS
        if keep.sum() < 200:
            # Too little agreement: better to fall back to single-view points than to return nothing,
            # but say so loudly because that cloud is noisier.
            log("[WARNING] Very few voxels are confirmed by 2+ stereo pairs; keeping single-pair points (noisier).")
            keep = np.ones_like(keep, dtype=bool)
            consistent = False
        else:
            consistent = True
        pos_mean, col_mean = pos_mean[keep], col_mean[keep]

        out = np.empty(len(pos_mean), dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"),
                                            ("red", "u1"), ("green", "u1"), ("blue", "u1")])
        out["x"], out["y"], out["z"] = pos_mean[:, 0], pos_mean[:, 1], pos_mean[:, 2]
        out["red"], out["green"], out["blue"] = np.clip(col_mean, 0, 255).astype(np.uint8).T
        raw_path = outputs_dir / "dense_cloud_raw.ply"
        plyfile.PlyData([plyfile.PlyElement.describe(out, "vertex")], text=False).write(str(raw_path))

        log(f"CPU stereo dense cloud: {len(out):,} points kept of {total_voxels:,} candidate voxels "
            f"({'confirmed by >=2 pairs' if consistent else 'single-pair, unconfirmed'}); {used_pairs} pairs used.")
        if volume is not None and matched_total > 0:
            log(f"Subject isolation (during stereo): {in_volume_total:,}/{matched_total:,} stereo points "
                f"({in_volume_total / matched_total * 100:.1f}%) were inside the SfM-verified volume; "
                f"{matched_total - in_volume_total:,} far-field points (distant terrain, sky) were discarded.")
        return {
            "subject_isolation": {
                "applied": volume is not None,
                "reason": None if volume is not None else "too few verified sparse points",
                "total_points": int(matched_total),
                "kept_points": int(in_volume_total),
                "removed_points": int(matched_total - in_volume_total),
                "kept_fraction": (in_volume_total / matched_total) if matched_total else None,
            },
            "dense_ply": str(raw_path),
            "dense_point_count": int(len(out)),
            "raw_dense_ply": str(raw_path),
            "raw_point_count": int(len(out)),
            "status": "completed",
            "reason": None,
            "method": "cpu_stereo_sgbm",
            "pairs_used": used_pairs,
            "multi_view_confirmed": consistent,
        }
