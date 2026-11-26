import os
import subprocess
import shutil
from app.core.presets import get_preset
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
from scipy.spatial import cKDTree
import plyfile

from app.services.colmap_service import ColmapService
from app.core.environment import check_colmap, check_colmap_dense_capable, check_gpu


class DenseService:
    @classmethod
    def filter_statistical_outliers(
        cls,
        input_path: Path,
        output_path: Path,
        k: int = 20,
        std_multiplier: float = 2.0,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Applies neighbourhood-based Statistical Outlier Removal (SOR) to a point cloud.
        k: number of nearest neighbours to analyze per point (default: 20)
        std_multiplier: standard deviation threshold multiplier (default: 2.0)
        Preserves original cloud completely untouched; writes filtered cloud to output_path.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input point cloud does not exist: {input_path}")

        p_data = plyfile.PlyData.read(str(input_path))
        if "vertex" not in p_data:
            raise ValueError(f"PLY file does not contain 'vertex' element: {input_path}")

        vertex_el = p_data["vertex"]
        raw_count = len(vertex_el)
        if raw_count == 0:
            raise ValueError("Input point cloud contains 0 vertices.")

        x = np.asarray(vertex_el["x"], dtype=np.float64)
        y = np.asarray(vertex_el["y"], dtype=np.float64)
        z = np.asarray(vertex_el["z"], dtype=np.float64)

        # 1. Quality Gate: Coordinate validity (NaN / Inf check)
        finite_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        finite_count = int(np.sum(finite_mask))
        if finite_count == 0:
            raise ValueError("All vertex coordinates are non-finite (NaN or Inf).")

        coords = np.column_stack([x, y, z])

        # Raw bounding box
        raw_min = [float(np.min(coords[finite_mask, 0])), float(np.min(coords[finite_mask, 1])), float(np.min(coords[finite_mask, 2]))]
        raw_max = [float(np.max(coords[finite_mask, 0])), float(np.max(coords[finite_mask, 1])), float(np.max(coords[finite_mask, 2]))]
        raw_span = [raw_max[i] - raw_min[i] for i in range(3)]

        # 2. Statistical Outlier Removal via SciPy cKDTree
        if finite_count < raw_count:
            valid_coords = coords[finite_mask]
        else:
            valid_coords = coords

        tree = cKDTree(valid_coords)
        actual_k = min(k, valid_coords.shape[0] - 1)
        distances, _ = tree.query(valid_coords, k=actual_k + 1, workers=-1)
        # Exclude self distance (index 0)
        mean_d = np.mean(distances[:, 1:], axis=1)
        mu = float(np.mean(mean_d))
        sigma = float(np.std(mean_d))
        thresh = mu + std_multiplier * sigma
        valid_inlier_mask = mean_d <= thresh

        if finite_count < raw_count:
            final_mask = np.zeros(raw_count, dtype=bool)
            final_mask[finite_mask] = valid_inlier_mask
        else:
            final_mask = valid_inlier_mask

        inlier_count = int(np.sum(final_mask))
        outlier_count = raw_count - inlier_count
        retention_ratio = inlier_count / max(raw_count, 1)

        # 3. Quality Gate Checks
        checks = {
            "all_finite": bool(finite_count == raw_count),
            "minimum_points": bool(inlier_count >= 100),
            "retention_threshold_passed": bool(retention_ratio >= 0.80),
            "spatial_span_valid": bool(all(s > 0 for s in raw_span))
        }

        # Filtered bounding box
        if inlier_count > 0:
            filt_min = [float(np.min(coords[final_mask, 0])), float(np.min(coords[final_mask, 1])), float(np.min(coords[final_mask, 2]))]
            filt_max = [float(np.max(coords[final_mask, 0])), float(np.max(coords[final_mask, 1])), float(np.max(coords[final_mask, 2]))]
            filt_span = [filt_max[i] - filt_min[i] for i in range(3)]
        else:
            filt_min = raw_min
            filt_max = raw_max
            filt_span = raw_span

        # 4. Write filtered PLY preserving all vertex properties and extra elements
        filtered_vertex_data = vertex_el.data[final_mask]
        new_vertex_el = plyfile.PlyElement.describe(filtered_vertex_data, "vertex")
        other_elements = [el for el in p_data.elements if el.name != "vertex"]
        new_ply = plyfile.PlyData([new_vertex_el] + other_elements, text=p_data.text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_ply.write(str(output_path))

        if log_callback:
            log_callback(
                f"Statistical Outlier Removal (k={k}, sigma={std_multiplier}): "
                f"Retained {inlier_count:,}/{raw_count:,} points ({retention_ratio * 100:.2f}%). "
                f"Pruned {outlier_count:,} outliers."
            )
            log_callback(
                f"Bounding box span tightened from "
                f"({raw_span[0]:.1f}, {raw_span[1]:.1f}, {raw_span[2]:.1f}) to "
                f"({filt_span[0]:.1f}, {filt_span[1]:.1f}, {filt_span[2]:.1f})."
            )

        gate_passed = checks["minimum_points"] and checks["retention_threshold_passed"]

        return {
            "status": "passed" if gate_passed else "flagged",
            "raw_points": raw_count,
            "filtered_points": inlier_count,
            "outliers_removed": outlier_count,
            "retention_percentage": round(retention_ratio * 100, 2),
            "raw_bounding_box": {"min": raw_min, "max": raw_max, "span": raw_span},
            "filtered_bounding_box": {"min": filt_min, "max": filt_max, "span": filt_span},
            "filtered_ply": str(output_path),
            "quality_gate": {
                "passed": gate_passed,
                "checks": checks
            }
        }
    @classmethod
    def postprocess_cloud(
        cls,
        raw_ply: Path,
        primary_sparse_model: Path,
        outputs_dir: Path,
        isolate_subject: bool = True,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Shared clean-up for ANY dense cloud (CUDA MVS or the CPU stereo fallback):
          1. subject isolation - drop points outside the SfM-verified volume (distant terrain/sky),
          2. statistical outlier removal.
        Inputs are never modified. Returns the path to use downstream and the stats of both steps.
        """
        from app.services.subject_service import SubjectService

        subject_stats: Dict[str, Any] = {"applied": False, "reason": "disabled in configuration"}
        source = raw_ply
        if isolate_subject:
            subject_stats = SubjectService.isolate_ply(
                input_ply=raw_ply,
                output_ply=outputs_dir / "dense_cloud_subject.ply",
                model_dir=primary_sparse_model,
                log_callback=log_callback
            )
            if subject_stats["applied"]:
                source = Path(subject_stats["output_ply"])

        filtered_ply_path = outputs_dir / "dense_cloud_filtered.ply"
        filter_stats = cls.filter_statistical_outliers(
            input_path=source,
            output_path=filtered_ply_path,
            k=20,
            std_multiplier=2.0,
            log_callback=log_callback
        )
        primary_output = filtered_ply_path if filter_stats["quality_gate"]["passed"] else source
        return {
            "path": primary_output,
            "point_count": filter_stats["filtered_points"] if primary_output == filtered_ply_path else subject_stats.get("kept_points"),
            "subject_stats": subject_stats,
            "filter_stats": filter_stats,
        }

    @classmethod
    def run_dense_reconstruction(
        cls,
        project_dir: Path,
        primary_sparse_model: Path,
        use_gpu: bool = True,
        isolate_subject: bool = True,
        quality_preset: str = "balanced",
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Executes genuine COLMAP Multi-View Stereo (MVS) dense reconstruction.
        Strictly requires image_undistorter, patch_match_stereo, and stereo_fusion.
        NEVER synthesizes or interpolates a fake dense cloud from sparse points.
        """
        mvs_dim = str(get_preset(quality_preset).mvs_dim)
        if not check_colmap().available:
            # No COLMAP program (SfM ran through pycolmap): MVS cannot run, the caller falls back to CPU stereo.
            reason = "COLMAP program not installed; dense MVS needs it (with CUDA)."
            if log_callback:
                log_callback(f"[NOTICE] {reason}")
            return {"dense_ply": None, "dense_point_count": 0, "status": "unsupported", "reason": reason}
        colmap_exe = ColmapService.get_colmap_executable()

        if not use_gpu:
            if log_callback:
                log_callback("[NOTICE] Battery-safe CPU mode active (or GPU disabled). Skipping CUDA-only patch_match_stereo.")
                log_callback("Dense MVS skipped; AI Depth completion and sparse SfM will generate the surface model.")
            return {
                "dense_ply": None,
                "dense_point_count": 0,
                "status": "skipped",
                "reason": "GPU acceleration disabled for battery safety. Running in CPU safe mode."
            }

        # 0. Check whether COLMAP executable supports dense stereo reconstruction
        dense_supported, dense_reason = check_colmap_dense_capable()
        if not dense_supported:
            if log_callback:
                log_callback(f"[NOTICE] Dense reconstruction unsupported: {dense_reason}")
                log_callback("Skipping dense stage; sparse SfM point cloud will be preserved as primary photogrammetric output.")
            return {
                "dense_ply": None,
                "dense_point_count": 0,
                "status": "unsupported",
                "reason": dense_reason
            }

        colmap_dir = project_dir / "colmap"
        dense_dir = colmap_dir / "dense"
        dense_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = project_dir / "frames"

        outputs_dir = project_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        dense_ply_path = outputs_dir / "dense_cloud.ply"

        if not primary_sparse_model.exists():
            err_msg = f"Primary sparse model path not found: {primary_sparse_model}"
            if log_callback:
                log_callback(f"[ERROR] {err_msg}")
            return {
                "dense_ply": None,
                "dense_point_count": 0,
                "status": "failed",
                "reason": err_msg
            }

        # 1. Image Undistortion
        undistort_cmd = [
            colmap_exe, "image_undistorter",
            "--image_path", str(frames_dir),
            "--input_path", str(primary_sparse_model),
            "--output_path", str(dense_dir),
            "--output_type", "COLMAP",
            "--max_image_size", mvs_dim
        ]
        if log_callback:
            log_callback(f"Undistorting images for dense stereo: {' '.join(undistort_cmd)}")

        proc = subprocess.run(undistort_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            if log_callback:
                log_callback(f"[ERROR] COLMAP image_undistorter failed (code {proc.returncode}): {err}")
            return {
                "dense_ply": None,
                "dense_point_count": 0,
                "status": "failed",
                "reason": f"image_undistorter failed: {err}"
            }

        # 2. Patch-Match Stereo
        patch_cmd = [
            colmap_exe, "patch_match_stereo",
            "--workspace_path", str(dense_dir),
            "--PatchMatchStereo.geom_consistency", "true",
            "--PatchMatchStereo.max_image_size", mvs_dim,
            "--PatchMatchStereo.cache_size", "16"
        ]
        if log_callback:
            log_callback(f"Running COLMAP patch-match stereo: {' '.join(patch_cmd)}")

        p_proc = subprocess.run(patch_cmd, capture_output=True, text=True)
        if p_proc.returncode != 0:
            err = p_proc.stderr.strip() or p_proc.stdout.strip()
            # If CUDA error occurs on battery, don't crash the entire job
            if any(k in err.lower() for k in ["cuda", "device", "out of memory"]):
                if log_callback:
                    log_callback(f"[WARNING] CUDA patch_match_stereo failed on GPU ({err}). Likely running on battery power without AC charger.")
                    log_callback("Gracefully proceeding: AI Depth densification and Delaunay meshing will complete the 3D model.")
                return {
                    "dense_ply": None,
                    "dense_point_count": 0,
                    "status": "unsupported",
                    "reason": f"CUDA error on battery power: {err}"
                }
            if log_callback:
                log_callback(f"[ERROR] COLMAP patch_match_stereo failed (code {p_proc.returncode}): {err}")
            return {
                "dense_ply": None,
                "dense_point_count": 0,
                "status": "failed",
                "reason": f"patch_match_stereo failed: {err}"
            }

        # 3. Stereo Fusion
        fused_ply_internal = dense_dir / "fused.ply"
        fuse_cmd = [
            colmap_exe, "stereo_fusion",
            "--workspace_path", str(dense_dir),
            "--output_path", str(fused_ply_internal),
            "--StereoFusion.max_image_size", mvs_dim
        ]
        if log_callback:
            log_callback(f"Running COLMAP stereo fusion: {' '.join(fuse_cmd)}")

        f_proc = subprocess.run(fuse_cmd, capture_output=True, text=True)
        if f_proc.returncode != 0 or not fused_ply_internal.exists() or fused_ply_internal.stat().st_size == 0:
            err = f_proc.stderr.strip() or f_proc.stdout.strip()
            if log_callback:
                log_callback(f"[ERROR] COLMAP stereo_fusion failed: {err}")
            return {
                "dense_ply": None,
                "dense_point_count": 0,
                "status": "failed",
                "reason": f"stereo_fusion failed: {err}"
            }

        # Validate fused cloud output
        try:
            p_data = plyfile.PlyData.read(str(fused_ply_internal))
            dense_points = len(p_data["vertex"])
            if dense_points == 0:
                raise ValueError("Fused dense cloud contains 0 vertices.")

            # Preserve immutable raw dense cloud
            raw_dense_path = outputs_dir / "dense_cloud_raw.ply"
            shutil.copy2(fused_ply_internal, raw_dense_path)
            shutil.copy2(fused_ply_internal, dense_ply_path)

            # Subject isolation (drop far-field background) + statistical outlier removal
            post = cls.postprocess_cloud(
                raw_ply=fused_ply_internal,
                primary_sparse_model=primary_sparse_model,
                outputs_dir=outputs_dir,
                isolate_subject=isolate_subject,
                log_callback=log_callback
            )
            filter_stats = post["filter_stats"]

            if log_callback:
                log_callback(
                    f"Genuine dense MVS stereo fusion completed: "
                    f"{dense_points:,} raw points, {post['point_count']:,} points after cleanup."
                )

            return {
                "dense_ply": str(post["path"]),
                "dense_point_count": post["point_count"],
                "raw_dense_ply": str(dense_ply_path),
                "raw_point_count": dense_points,
                "filter_stats": filter_stats,
                "subject_isolation": post["subject_stats"],
                "status": "completed",
                "reason": None
            }
        except Exception as e:
            if log_callback:
                log_callback(f"[ERROR] Failed to validate fused dense cloud: {e}")
            return {
                "dense_ply": None,
                "dense_point_count": 0,
                "status": "failed",
                "reason": f"Dense cloud validation error: {e}"
            }
