import cv2
import numpy as np
import plyfile
from app.core.presets import get_preset
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from app.config import settings
from app.services.colmap_service import ColmapService
from app.services.dense_service import DenseService


class AiDepthService:
    _session = None
    MIN_ALIGNMENT_INLIERS = 8
    # AI points are only kept where the photogrammetric cloud has a gap larger than this many
    # typical point spacings; elsewhere the measured MVS points win.
    VOID_FILL_SPACING_FACTOR = 3.0

    @staticmethod
    def _vertex_xyz_rgb(vertex_el) -> Tuple[np.ndarray, np.ndarray]:
        """Extract (N,3) float32 xyz and (N,3) uint8 rgb from a PLY vertex element, ignoring extra fields (e.g. normals)."""
        names = vertex_el.data.dtype.names
        pts = np.column_stack([vertex_el["x"], vertex_el["y"], vertex_el["z"]]).astype(np.float32)
        if all(c in names for c in ("red", "green", "blue")):
            cols = np.column_stack([vertex_el["red"], vertex_el["green"], vertex_el["blue"]]).astype(np.uint8)
        else:
            cols = np.full((len(pts), 3), 160, dtype=np.uint8)
        return pts, cols

    @classmethod
    def select_void_filling_points(
        cls,
        base_pts: np.ndarray,
        ai_pts: np.ndarray,
        spacing_factor: Optional[float] = None
    ) -> np.ndarray:
        """
        Boolean mask over ai_pts: True where the AI point lies in a gap of the measured cloud.
        AI depth is an estimate; stacking it on top of good MVS points produces doubled 'ghost'
        surfaces, so it is only allowed to fill where no measured points exist.
        """
        from scipy.spatial import cKDTree
        factor = spacing_factor if spacing_factor is not None else cls.VOID_FILL_SPACING_FACTOR
        if len(base_pts) < 10 or len(ai_pts) == 0:
            return np.ones(len(ai_pts), dtype=bool)
        tree = cKDTree(base_pts)
        rng = np.random.default_rng(0)
        sample = base_pts[rng.choice(len(base_pts), size=min(len(base_pts), 20000), replace=False)]
        nn, _ = tree.query(sample, k=2, workers=-1)
        spacing = float(np.median(nn[:, 1]))
        d, _ = tree.query(ai_pts, workers=-1)
        return d > spacing * factor

    @classmethod
    def get_model_path(cls) -> Path:
        candidates = [
            Path(__file__).resolve().parents[3] / "bin" / "models" / "depth_anything_v2" / "model.onnx",
            settings.BIRDS_EYE_WORKSPACE.parent / "bin" / "models" / "depth_anything_v2" / "model.onnx",
            Path("bin/models/depth_anything_v2/model.onnx").resolve(),
            Path("e:/yashu/proj/BIRDS_EYE/bin/models/depth_anything_v2/model.onnx"),
        ]
        for cand in candidates:
            if cand.exists():
                return cand
        return candidates[0]

    @classmethod
    def is_available(cls) -> Tuple[bool, str]:
        """Check if ONNX runtime and Depth Anything V2 weights are available."""
        try:
            pass
        except ImportError:
            return False, "onnxruntime is not installed in the environment."

        model_path = cls.get_model_path()
        if not model_path.exists():
            return False, f"Depth Anything V2 model weights not found at {model_path}. Run: python tools/download_depth_model.py"

        return True, "Depth Anything V2 ONNX is ready."

    @classmethod
    def _get_inference_session(cls):
        """Loads and caches the ONNX Runtime inference session."""
        if cls._session is None:
            import onnxruntime as ort
            model_path = cls.get_model_path()
            if not model_path.exists():
                raise FileNotFoundError(f"Model file not found: {model_path}")
            # Use CPU execution provider for guaranteed compatibility
            cls._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        return cls._session

    @classmethod
    def predict_disparity(cls, image_bgr: np.ndarray, target_size: int = 518) -> np.ndarray:
        """
        Runs Depth Anything V2 inference on an RGB image.
        Returns a normalized disparity (inverse depth) map matching the input image shape (H, W).
        """
        session = cls._get_inference_session()
        orig_h, orig_w = image_bgr.shape[:2]

        # Resize to multiples of 14 preserving aspect ratio
        target_h = int(np.round(orig_h * target_size / max(orig_h, orig_w) / 14) * 14)
        target_w = int(np.round(orig_w * target_size / max(orig_h, orig_w) / 14) * 14)
        resized = cv2.resize(image_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # ImageNet normalization
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        norm_img = ((rgb - mean) / std).transpose(2, 0, 1)[None, ...].astype(np.float32)

        # Inference
        # Different ONNX exports name their tensors differently (HF: pixel_values/predicted_depth, others: image/depth);
        # hard-coding one export made every other model crash. Use whatever this model declares.
        in_name = session.get_inputs()[0].name
        out_name = session.get_outputs()[0].name
        outputs = session.run([out_name], {in_name: norm_img})
        disparity_low = np.squeeze(outputs[0]).astype(np.float32)
        if disparity_low.ndim != 2:
            raise RuntimeError(f"Unexpected depth output shape {outputs[0].shape}; expected one (H, W) map.")

        # Upscale back to original image resolution
        disparity_full = cv2.resize(disparity_low, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        return disparity_full

    @classmethod
    def align_scale_and_shift(
        cls,
        disparity_map: np.ndarray,
        points2d: np.ndarray,
        camera_depths: np.ndarray
    ) -> Tuple[float, float, int]:
        """
        Robustly solves metric scale (s) and shift (o) using RANSAC:
        1 / Z_metric = s * disparity + o
        """
        if len(points2d) < 4:
            # Fallback to median depth heuristic if sparse points are sparse
            med_depth = float(np.median(camera_depths)) if len(camera_depths) > 0 else 10.0
            med_disp = float(np.median(disparity_map))
            scale = (1.0 / med_depth) / max(med_disp, 1e-4)
            return scale, 0.0, len(points2d)

        h, w = disparity_map.shape[:2]
        sampled_disp = []
        valid_inv_depths = []

        for pt, z in zip(points2d, camera_depths):
            x, y = int(round(pt[0])), int(round(pt[1]))
            if 0 <= x < w and 0 <= y < h and z > 0.1:
                disp_val = float(disparity_map[y, x])
                if disp_val > 0.01:
                    sampled_disp.append(disp_val)
                    valid_inv_depths.append(1.0 / z)

        if len(sampled_disp) < 4:
            med_depth = float(np.median(camera_depths)) if len(camera_depths) > 0 else 10.0
            return (1.0 / med_depth), 0.0, len(sampled_disp)

        X = np.array(sampled_disp)
        Y = np.array(valid_inv_depths)

        # Robust RANSAC 1D Linear Fit
        best_inliers = 0
        best_s, best_o = 1.0, 0.0
        rng = np.random.default_rng(0)          # deterministic: same video -> same model
        n_pts = len(X)
        iterations = min(100, max(20, n_pts * 2))

        for _ in range(iterations):
            idx = rng.choice(n_pts, 2, replace=False)
            x0, x1 = X[idx[0]], X[idx[1]]
            y0, y1 = Y[idx[0]], Y[idx[1]]
            if abs(x1 - x0) < 1e-6:
                continue

            s = (y1 - y0) / (x1 - x0)
            if s <= 0:  # Higher disparity must correspond to higher inverse depth (closer)
                continue
            o = y0 - s * x0

            pred_y = s * X + o
            residuals = np.abs(Y - pred_y) / (Y + 1e-6)
            inliers = int(np.sum(residuals < 0.25))  # Within 25% relative error

            if inliers > best_inliers:
                best_inliers = inliers
                best_s, best_o = s, o

        if best_s <= 0 or best_inliers < 2:
            # Fallback
            med_depth = float(np.median(camera_depths))
            best_s = (1.0 / med_depth) / max(float(np.median(X)), 1e-4)
            best_o = 0.0

        return float(best_s), float(best_o), best_inliers

    @classmethod
    def backproject_dense_points(
        cls,
        image_bgr: np.ndarray,
        disparity_map: np.ndarray,
        scale: float,
        shift: float,
        focal_len: float,
        cx: float,
        cy: float,
        R_cam: np.ndarray,
        t_cam: np.ndarray,
        stride: int = 8,
        min_disparity_thresh: float = 0.05
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Backprojects pixels with valid metric depth into 3D world coordinates.
        Returns: (points_world Nx3, colors_rgb Nx3)
        """
        h, w = disparity_map.shape[:2]

        # Subsample grid by stride to keep point cloud dense but fast
        ys, xs = np.mgrid[0:h:stride, 0:w:stride]
        disp_sub = disparity_map[ys, xs]
        bgr_sub = image_bgr[ys, xs]

        # Mask out sky / distant background. Depth Anything's raw output has no fixed range, so the
        # threshold is applied on a per-image 0..1 rescale (2nd-98th percentile) rather than on raw
        # values (the old absolute 0.15 cut meant very different things on different images).
        lo, hi = np.percentile(disparity_map, [2, 98])
        if (hi - lo) < 1e-6 * max(abs(float(hi)), 1.0):
            # Degenerate (constant) depth map: there is no far/near contrast to mask a sky with, so
            # keep every pixel; non-positive depths are still rejected below.
            valid_mask = np.ones_like(disp_sub, dtype=bool)
        else:
            rel_disp = np.clip((disp_sub - lo) / float(hi - lo), 0.0, 1.0)
            valid_mask = rel_disp > min_disparity_thresh
        if not np.any(valid_mask):
            return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint8)

        disp_valid = disp_sub[valid_mask]
        u_valid = xs[valid_mask].astype(np.float32)
        v_valid = ys[valid_mask].astype(np.float32)
        bgr_valid = bgr_sub[valid_mask]

        # Compute metric depth Z = 1 / (s * disparity + o)
        inv_z = scale * disp_valid + shift
        # Filter negative or degenerate depths
        depth_mask = inv_z > 1e-5
        if not np.any(depth_mask):
            return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint8)

        z_cam = 1.0 / inv_z[depth_mask]
        # Restrict depth to reasonable photogrammetric distance
        max_dist = 500.0
        dist_mask = z_cam < max_dist

        if not np.any(dist_mask):
            return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint8)

        z = z_cam[dist_mask]
        u = u_valid[depth_mask][dist_mask]
        v = v_valid[depth_mask][dist_mask]
        colors = cv2.cvtColor(bgr_valid[depth_mask][dist_mask][None, ...], cv2.COLOR_BGR2RGB)[0]

        # Camera coordinate points:
        x_cam = (u - cx) * z / focal_len
        y_cam = (v - cy) * z / focal_len
        pts_cam = np.column_stack([x_cam, y_cam, z])

        # World coordinates: P_world = R^T * (P_cam - t)
        pts_world = np.dot(pts_cam - t_cam, R_cam)

        return pts_world.astype(np.float32), colors.astype(np.uint8)

    @classmethod
    def run_ai_densification(
        cls,
        project_dir: Path,
        primary_sparse_dir: Path,
        max_frames: Optional[int] = None,
        stride: Optional[int] = None,
        quality_preset: str = "balanced",
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Executes Approach 1: Monocular AI Depth surface completion and densification.
        Combines COLMAP camera poses with Depth Anything V2 to fill glass, water, and missing facades.
        """
        preset = get_preset(quality_preset)
        max_frames = max_frames or preset.ai_frames
        stride = stride or preset.ai_stride
        available, reason = cls.is_available()
        if not available:
            if log_callback:
                log_callback(f"[ERROR] AI depth completion unavailable: {reason}")
            return {"status": "failed", "reason": reason}

        frames_dir = project_dir / "frames"
        outputs_dir = project_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        images_txt = primary_sparse_dir / "images.txt"
        cameras_txt = primary_sparse_dir / "cameras.txt"
        points3d_txt = primary_sparse_dir / "points3D.txt"

        if not images_txt.exists() or not cameras_txt.exists() or not points3d_txt.exists():
            err = f"Sparse model text files missing in {primary_sparse_dir}"
            if log_callback:
                log_callback(f"[ERROR] {err}")
            return {"status": "failed", "reason": err}

        if log_callback:
            log_callback("Initializing Depth Anything V2 monocular depth engine...")

        # 1. Parse camera intrinsics
        focal_len, cx, cy = 1000.0, 960.0, 540.0
        cam_w = cam_h = None
        with open(cameras_txt, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split()
                    # e.g. 1 SIMPLE_RADIAL 3840 2160 f cx cy k
                    if len(parts) >= 7:
                        cam_w, cam_h = float(parts[2]), float(parts[3])
                        focal_len = float(parts[4])
                        cx = float(parts[5])
                        cy = float(parts[6])
                        break

        # 2. Parse sparse 3D points
        points3d = {}
        with open(points3d_txt, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split()
                    pid = int(parts[0])
                    xyz = np.array([float(parts[1]), float(parts[2]), float(parts[3])])
                    points3d[pid] = xyz

        # 3. Parse registered images and their visible 3D points
        registered_images = []
        with open(images_txt, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

        for i in range(0, len(lines), 2):
            meta = lines[i].split()
            pts2d_raw = lines[i+1].split() if i+1 < len(lines) else []

            img_id = int(meta[0])
            qw, qx, qy, qz = map(float, meta[1:5])
            tx, ty, tz = map(float, meta[5:8])
            img_name = meta[9]

            R = ColmapService.qvec2rotmat([qw, qx, qy, qz])
            t = np.array([tx, ty, tz])

            # Extract 2D-3D correspondences
            pts2d_list = []
            depths_list = []
            for j in range(0, len(pts2d_raw), 3):
                u = float(pts2d_raw[j])
                v = float(pts2d_raw[j+1])
                p3d_id = int(pts2d_raw[j+2])
                if p3d_id in points3d:
                    P_w = points3d[p3d_id]
                    # Z in camera space
                    P_c = np.dot(R, P_w) + t
                    if P_c[2] > 0.1:
                        pts2d_list.append([u, v])
                        depths_list.append(P_c[2])

            registered_images.append({
                "id": img_id,
                "name": img_name,
                "R": R,
                "t": t,
                "pts2d": np.array(pts2d_list),
                "depths": np.array(depths_list)
            })

        if not registered_images:
            return {"status": "failed", "reason": "No registered camera views found in sparse model."}

        # Select evenly distributed keyframes up to max_frames
        total_reg = len(registered_images)
        step = max(1, total_reg // max_frames)
        selected_views = registered_images[::step][:max_frames]

        if log_callback:
            log_callback(f"Densifying scene across {len(selected_views)} selected drone keyframes...")

        all_world_pts = []
        all_colors = []

        for idx, view in enumerate(selected_views):
            img_file = frames_dir / view["name"]
            if not img_file.exists():
                continue

            img_bgr = cv2.imread(str(img_file))
            if img_bgr is None:
                continue

            # The camera model was solved at the SfM image size; if the frame on disk differs, scale the intrinsics with it.
            f_img, cx_img, cy_img = focal_len, cx, cy
            if cam_w and cam_h and (img_bgr.shape[1] != int(cam_w) or img_bgr.shape[0] != int(cam_h)):
                k = img_bgr.shape[1] / cam_w
                f_img, cx_img, cy_img = focal_len * k, cx * k, cy * k
                view["pts2d"] = view["pts2d"] * k if len(view["pts2d"]) else view["pts2d"]

            # Predict AI disparity
            try:
                disp = cls.predict_disparity(img_bgr, target_size=518)
            except Exception as exc:
                return {"status": "failed", "reason": f"Depth model could not run ({exc}). Is model.onnx a Depth Anything V2 export?"}

            # Align scale and shift using sparse points
            scale, shift, inliers = cls.align_scale_and_shift(disp, view["pts2d"], view["depths"])

            # A monocular depth map is only trustworthy once it has been tied to the SfM scale by
            # enough sparse points. With too few inliers the scale is a guess and the view would
            # back-project as a misplaced "ghost" layer, so skip it rather than pollute the cloud.
            if inliers < cls.MIN_ALIGNMENT_INLIERS:
                if log_callback:
                    log_callback(
                        f"View {idx+1}/{len(selected_views)} ({view['name']}): skipped - only {inliers} sparse points "
                        f"support the depth alignment (need {cls.MIN_ALIGNMENT_INLIERS})."
                    )
                continue

            # Backproject into 3D world space
            pts_w, cols_rgb = cls.backproject_dense_points(
                image_bgr=img_bgr,
                disparity_map=disp,
                scale=scale,
                shift=shift,
                focal_len=f_img,
                cx=cx_img,
                cy=cy_img,
                R_cam=view["R"],
                t_cam=view["t"],
                stride=stride
            )

            if len(pts_w) > 0:
                all_world_pts.append(pts_w)
                all_colors.append(cols_rgb)

            if log_callback:
                log_callback(
                    f"View {idx+1}/{len(selected_views)} ({view['name']}): "
                    f"Generated {len(pts_w):,} surface points (inliers: {inliers})."
                )

        if not all_world_pts:
            return {"status": "failed", "reason": "No valid 3D points were backprojected from AI depth maps."}

        merged_pts = np.vstack(all_world_pts)
        merged_cols = np.vstack(all_colors)

        if log_callback:
            log_callback(f"Aggregated {len(merged_pts):,} raw AI surface points. Applying statistical outlier filter...")

        # Write intermediate raw AI cloud
        raw_ai_ply = outputs_dir / "dense_cloud_ai_raw.ply"
        filtered_ai_ply = outputs_dir / "dense_cloud_ai.ply"

        vertex_dtype = [
            ('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
            ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')
        ]
        arr = np.empty(len(merged_pts), dtype=vertex_dtype)
        for i, col in enumerate(('x', 'y', 'z')):
            arr[col] = merged_pts[:, i]
        for i, col in enumerate(('red', 'green', 'blue')):
            arr[col] = merged_cols[:, i]

        el = plyfile.PlyElement.describe(arr, 'vertex')
        plyfile.PlyData([el], text=False).write(str(raw_ai_ply))

        # Filter statistical outliers
        filter_res = DenseService.filter_statistical_outliers(
            input_path=raw_ai_ply,
            output_path=filtered_ai_ply,
            k=20,
            std_multiplier=2.0,
            log_callback=log_callback
        )

        # Merge with existing photogrammetric dense cloud if available
        dense_filtered = outputs_dir / "dense_cloud_filtered.ply"
        fused_ai_ply = outputs_dir / "dense_cloud_fused_ai.ply"
        total_fused_points = filter_res["filtered_points"]

        if dense_filtered.exists():
            try:
                base_data = plyfile.PlyData.read(str(dense_filtered))
                filt_data = plyfile.PlyData.read(str(filtered_ai_ply))

                # COLMAP's fused.ply carries normals (nx,ny,nz); the AI cloud does not. Concatenating
                # the raw structured arrays therefore raises, and the old code swallowed that error and
                # silently dropped the MVS cloud. Rebuild both on a common x,y,z,r,g,b layout instead.
                base_pts, base_cols = cls._vertex_xyz_rgb(base_data["vertex"])
                ai_pts, ai_cols = cls._vertex_xyz_rgb(filt_data["vertex"])

                keep = cls.select_void_filling_points(base_pts, ai_pts)
                ai_pts, ai_cols = ai_pts[keep], ai_cols[keep]

                all_pts = np.vstack([base_pts, ai_pts])
                all_cols = np.vstack([base_cols, ai_cols])
                combined_v = np.empty(len(all_pts), dtype=vertex_dtype)
                for i, col in enumerate(("x", "y", "z")):
                    combined_v[col] = all_pts[:, i]
                for i, col in enumerate(("red", "green", "blue")):
                    combined_v[col] = all_cols[:, i]

                comb_el = plyfile.PlyElement.describe(combined_v, 'vertex')
                plyfile.PlyData([comb_el], text=False).write(str(fused_ai_ply))
                total_fused_points = len(combined_v)

                if log_callback:
                    log_callback(
                        f"Merged {len(base_pts):,} measured MVS points with {len(ai_pts):,} AI points that fill gaps "
                        f"(AI points overlapping measured surface were discarded) -> {total_fused_points:,} total points."
                    )
            except Exception as e:
                if log_callback:
                    log_callback(f"[WARNING] Failed to merge with base cloud: {e}")

        final_ply = fused_ai_ply if fused_ai_ply.exists() else filtered_ai_ply

        # Monocular depth has no real scale far away: sky and distant terrain come out as huge sheets.
        # Keep only what lies inside the SfM-verified volume (same rule as the MVS cloud).
        subject_stats = None
        try:
            from app.services.subject_service import SubjectService
            tmp_ply = final_ply.with_name(final_ply.stem + "_subject_tmp.ply")
            subject_stats = SubjectService.isolate_ply(final_ply, tmp_ply, primary_sparse_dir, log_callback=log_callback)
            if subject_stats.get("applied") and tmp_ply.exists():
                tmp_ply.replace(final_ply)
                total_fused_points = subject_stats["kept_points"]
            elif tmp_ply.exists():
                tmp_ply.unlink()
        except Exception as e:
            if log_callback:
                log_callback(f"[WARNING] Subject isolation of the AI cloud failed: {e}")

        return {
            "status": "completed",
            "ai_points": filter_res["filtered_points"],
            "total_points": total_fused_points,
            "ai_ply_path": str(final_ply),
            # job_manager reads this key to register the output file (it previously looked for a key
            # that did not exist, so the AI cloud was never listed as a stage output).
            "fused_cloud_ply": str(final_ply),
            "filter_stats": filter_res,
            "subject_isolation": subject_stats
        }

