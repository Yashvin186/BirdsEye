import subprocess
import shutil
import json
from app.core.presets import get_preset
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import plyfile

from app.core.environment import check_colmap
from app.services.pycolmap_engine import PyColmapEngine


class ColmapService:
    @classmethod
    def use_pycolmap(cls) -> bool:
        """True when the COLMAP program is missing but the pycolmap package can do SfM instead."""
        return (not check_colmap().available) and PyColmapEngine.available()

    @staticmethod
    def write_sparse_ply_from_text(points_txt: Path, output_ply: Path) -> None:
        """Write the sparse cloud (x,y,z,r,g,b) from a COLMAP text model's points3D.txt."""
        rows = []
        with open(points_txt, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line or line.startswith("#"):
                    continue
                p = line.split()
                if len(p) >= 8:
                    rows.append((float(p[1]), float(p[2]), float(p[3]), int(p[4]), int(p[5]), int(p[6])))
        v = np.zeros(len(rows), dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"),
                                       ("red", "u1"), ("green", "u1"), ("blue", "u1")])
        for i, r in enumerate(rows):
            v[i] = r
        output_ply.parent.mkdir(parents=True, exist_ok=True)
        plyfile.PlyData([plyfile.PlyElement.describe(v, "vertex")]).write(str(output_ply))

    @classmethod
    def get_colmap_executable(cls) -> str:
        info = check_colmap()
        if not info.available or not info.path:
            raise RuntimeError(
                "COLMAP executable is not available on PATH or configured location. "
                "Feature matching and Structure-from-Motion require COLMAP."
            )
        return info.path

    @classmethod
    def run_feature_extraction(
        cls,
        project_dir: Path,
        use_gpu: bool = True,
        quality_preset: str = "balanced",
        log_callback=None
    ) -> Dict[str, Any]:
        preset = get_preset(quality_preset)
        if cls.use_pycolmap():
            return PyColmapEngine.extract_features(project_dir, quality_preset, use_gpu, log_callback)
        colmap_exe = cls.get_colmap_executable()
        colmap_dir = project_dir / "colmap"
        colmap_dir.mkdir(parents=True, exist_ok=True)
        db_path = colmap_dir / "database.db"

        # Remove previous db if re-running
        for suffix in ("", "-wal", "-shm"):          # stale WAL/SHM files from a killed run lock the new database
            stale = db_path.with_name(db_path.name + suffix)
            if stale.exists():
                stale.unlink()

        frames_dir = project_dir / "frames"
        image_files = sorted(frames_dir.glob("frame_*.jpg"))
        if not image_files:
            raise ValueError("No accepted frames found to run COLMAP feature extraction.")
        if len(image_files) < 3:
            raise ValueError(
                f"COLMAP photogrammetry requires at least 3 accepted frames, but only found {len(image_files)}. "
                "Please adjust frame sampling or reduce blur/duplicate thresholds to retain more frames."
            )

        # Write explicit image list containing ONLY actual frames so COLMAP
        # never attempts to read contact sheets or manifest metadata.
        image_list_path = colmap_dir / "image_list.txt"
        with open(image_list_path, "w", encoding="utf-8") as f:
            for img in image_files:
                f.write(f"{img.name}\n")

        cmd = [
            colmap_exe, "feature_extractor",
            "--database_path", str(db_path),
            "--image_path", str(frames_dir),
            "--image_list_path", str(image_list_path),
            "--ImageReader.camera_model", "SIMPLE_RADIAL",
            "--ImageReader.single_camera", "1",
            "--SiftExtraction.use_gpu", "1" if use_gpu else "0",
            "--SiftExtraction.max_image_size", str(preset.sift_dim),
            "--SiftExtraction.max_num_features", str(preset.sift_features)
        ]

        if log_callback:
            log_callback(f"Executing: {' '.join(cmd)}")

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            # If failed on CUDA/GPU error and use_gpu was True, auto-fallback to CPU
            if use_gpu and any(k in err.lower() for k in ["cuda", "device", "out of memory"]):
                if log_callback:
                    log_callback("[WARNING] CUDA GPU initialization failed (running on battery or low power). Retrying SIFT feature extraction in CPU safe mode...")
                cmd[-1] = "0"
                if db_path.exists():
                    db_path.unlink()
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    err = proc.stderr.strip() or proc.stdout.strip()
                    raise RuntimeError(f"COLMAP feature extraction failed on CPU retry (code {proc.returncode}): {err}")
            else:
                raise RuntimeError(f"COLMAP feature extraction failed (code {proc.returncode}): {err}")

        if not db_path.exists() or db_path.stat().st_size == 0:
            raise RuntimeError("COLMAP feature extractor finished but database.db is missing or empty.")

        if log_callback:
            log_callback(f"COLMAP feature extraction completed successfully for {len(image_files)} frames.")

        return {"database_path": str(db_path), "database_size_bytes": db_path.stat().st_size, "frame_count": len(image_files)}

    @classmethod
    def run_feature_matching(
        cls,
        project_dir: Path,
        strategy: str = "sequential",
        use_gpu: bool = True,
        log_callback=None
    ) -> Dict[str, Any]:
        if cls.use_pycolmap():
            if not (project_dir / "colmap" / "database.db").exists():
                raise FileNotFoundError("COLMAP database.db not found. Feature extraction must precede matching.")
            return PyColmapEngine.match(project_dir, strategy, use_gpu, log_callback)
        colmap_exe = cls.get_colmap_executable()
        colmap_dir = project_dir / "colmap"
        db_path = colmap_dir / "database.db"

        if not db_path.exists():
            raise FileNotFoundError("COLMAP database.db not found. Feature extraction must precede matching.")

        matcher_cmd = "sequential_matcher" if strategy == "sequential" else "exhaustive_matcher"
        cmd = [
            colmap_exe, matcher_cmd,
            "--database_path", str(db_path),
            "--SiftMatching.use_gpu", "1" if use_gpu else "0"
        ]

        if strategy == "sequential":
            cmd.extend(["--SequentialMatching.overlap", "10", "--SequentialMatching.quadratic_overlap", "1"])

        if log_callback:
            log_callback(f"Executing: {' '.join(cmd)}")

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            # If failed on CUDA/GPU error and use_gpu was True, auto-fallback to CPU
            if use_gpu and any(k in err.lower() for k in ["cuda", "device", "out of memory"]):
                if log_callback:
                    log_callback("[WARNING] CUDA GPU matching failed (battery or power throttling). Retrying feature matching in CPU safe mode...")
                # Flip the VALUE that follows the flag. (The old code overwrote cmd[4], which is the
                # flag name itself, producing an invalid command so the CPU retry could never succeed.)
                gpu_flag_idx = cmd.index("--SiftMatching.use_gpu")
                cmd[gpu_flag_idx + 1] = "0"
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    err = proc.stderr.strip() or proc.stdout.strip()
                    raise RuntimeError(f"COLMAP {matcher_cmd} failed on CPU retry (code {proc.returncode}): {err}")
            else:
                raise RuntimeError(f"COLMAP {matcher_cmd} failed (code {proc.returncode}): {err}")

        if log_callback:
            log_callback("COLMAP feature matching completed successfully.")

        return {"matcher": matcher_cmd, "database_path": str(db_path)}

    @classmethod
    def run_sparse_sfm(
        cls,
        project_dir: Path,
        log_callback=None
    ) -> Dict[str, Any]:
        use_py = cls.use_pycolmap()
        colmap_exe = None if use_py else cls.get_colmap_executable()
        colmap_dir = project_dir / "colmap"
        db_path = colmap_dir / "database.db"
        frames_dir = project_dir / "frames"
        sparse_dir = colmap_dir / "sparse"
        sparse_dir.mkdir(parents=True, exist_ok=True)
        image_list_path = colmap_dir / "image_list.txt"

        # Clear old sparse output
        for item in sparse_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        if use_py:
            PyColmapEngine.map(project_dir, sparse_dir, log_callback)
        else:
            cmd = [
                colmap_exe, "mapper",
                "--database_path", str(db_path),
                "--image_path", str(frames_dir),
                "--output_path", str(sparse_dir),
                "--Mapper.init_min_tri_angle", "1.5",
                "--Mapper.init_min_num_inliers", "15",
                "--Mapper.init_max_forward_motion", "0.99",
                "--Mapper.init_max_error", "8.0",
                "--Mapper.ba_refine_focal_length", "1",
                "--Mapper.ba_refine_extra_params", "1"
            ]
            if image_list_path.exists():
                cmd.extend(["--image_list_path", str(image_list_path)])

            if log_callback:
                log_callback(f"Executing: {' '.join(cmd)}")

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                err = proc.stderr.strip() or proc.stdout.strip()
                raise RuntimeError(f"COLMAP mapper failed (code {proc.returncode}): {err}")


        # Check reconstructed submodels
        submodels = [
            d for d in sparse_dir.iterdir()
            if d.is_dir() and ((d / "cameras.bin").exists() or (d / "cameras.txt").exists())
        ]
        if not submodels:
            raise RuntimeError(
                "COLMAP Structure-from-Motion could not reconstruct any 3D points. "
                "Footage may lack sufficient parallax, visual overlap, or sharp texture."
            )

        # Analyze and rank all reconstructed submodels
        submodel_stats = []
        for d in submodels:
            stat = cls.analyze_submodel(colmap_exe, d)
            submodel_stats.append(stat)

        # Deterministic ranking: prefer highest registered camera count, then point count
        submodel_stats.sort(key=lambda s: (s["registered_cams"], s["point_count"]), reverse=True)
        primary_stats = submodel_stats[0]
        primary_model = primary_stats["path"]

        outputs_dir = project_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        sparse_ply_path = outputs_dir / "sparse_cloud.ply"

        # Export PLY of the sparse cloud
        if use_py:
            cls.write_sparse_ply_from_text(primary_model / "points3D.txt", sparse_ply_path)
            if log_callback:
                log_callback(f"Exporting primary sparse model ({primary_stats['registered_cams']} cams, {primary_stats['point_count']} pts).")
        else:
            # Export PLY using model_converter
            conv_cmd = [
                colmap_exe, "model_converter",
                "--input_path", str(primary_model),
                "--output_path", str(sparse_ply_path),
                "--output_type", "PLY"
            ]
            if log_callback:
                log_callback(f"Exporting primary sparse model ({primary_stats['registered_cams']} cams, {primary_stats['point_count']} pts): {' '.join(conv_cmd)}")

            conv_proc = subprocess.run(conv_cmd, capture_output=True, text=True)
            if conv_proc.returncode != 0:
                err = conv_proc.stderr.strip() or conv_proc.stdout.strip()
                raise RuntimeError(f"COLMAP model_converter failed: {err}")


        # Parse PLY statistics
        point_count = 0
        if sparse_ply_path.exists():
            try:
                plydata = plyfile.PlyData.read(str(sparse_ply_path))
                point_count = len(plydata["vertex"])
            except Exception:
                point_count = primary_stats["point_count"]
        else:
            point_count = primary_stats["point_count"]

        # Extract drone camera trajectory and orientations for 3D viewer
        cameras_json_path = outputs_dir / "cameras.json"
        cameras_list = cls.extract_camera_trajectory(primary_model / "images.txt", cameras_json_path)

        total_frames = len(list(frames_dir.glob("frame_*.jpg")))
        registered_frames = primary_stats["registered_cams"]
        reg_percentage = round((registered_frames / total_frames * 100), 1) if total_frames > 0 else 0.0

        # Objective quality signals. These are what actually explain "smeared" or "sheet-like"
        # clouds, so surface them instead of only reporting point counts.
        sfm_warnings: List[str] = []
        if reg_percentage < 60.0:
            sfm_warnings.append(
                f"Only {registered_frames}/{total_frames} frames ({reg_percentage}%) registered. "
                "Unregistered frames contribute nothing, so large parts of the scene may be missing or fragmented."
            )
        if len(submodels) > 1:
            sfm_warnings.append(
                f"SfM split the flight into {len(submodels)} disconnected models; only the best one is used. "
                "This usually means overlap between consecutive frames broke down (too fast, too blurry, or too few frames)."
            )
        err = primary_stats.get("mean_reproj_error_px")
        if err is not None and err > 1.5:
            sfm_warnings.append(
                f"Mean reprojection error is {err} px (healthy is typically < 1 px). "
                "Camera poses are likely inaccurate, which produces smeared or doubled geometry downstream."
            )
        track = primary_stats.get("mean_track_length")
        if track is not None and track < 3.0:
            sfm_warnings.append(
                f"Mean feature track length is {track} frames (very short). Points are seen from too few views "
                "to be triangulated reliably; increase frame overlap (higher sampling FPS) or fly slower."
            )

        if log_callback:
            log_callback(
                f"Sparse SfM completed: Selected primary model '{primary_model.name}' with {point_count} 3D points, "
                f"{registered_frames}/{total_frames} frames registered ({reg_percentage}%). "
                f"Total submodels: {len(submodels)}. "
                f"Mean reprojection error: {err} px, mean track length: {track}."
            )
            for w in sfm_warnings:
                log_callback(f"[WARNING] {w}")

        return {
            "warnings": sfm_warnings,
            "mean_reproj_error_px": err,
            "mean_track_length": track,
            "sparse_ply": str(sparse_ply_path),
            "cameras_json": str(cameras_json_path) if cameras_json_path.exists() else None,
            "cameras_count": len(cameras_list),
            "point_count": point_count,
            "registered_frames": registered_frames,
            "total_frames": total_frames,
            "registration_percent": reg_percentage,
            "submodels_count": len(submodels),
            "submodels_summary": [
                {"name": s["name"], "registered_cams": s["registered_cams"], "points": s["point_count"]}
                for s in submodel_stats
            ],
            "primary_model_path": str(primary_model.resolve())
        }

    @classmethod
    def analyze_submodel(cls, colmap_exe: str, m_dir: Path) -> Dict[str, Any]:
        """Ensures TXT format exists and returns registered camera count and 3D point count."""
        images_txt = m_dir / "images.txt"
        points_txt = m_dir / "points3D.txt"

        if not images_txt.exists() or not points_txt.exists():
            txt_cmd = [
                colmap_exe, "model_converter",
                "--input_path", str(m_dir),
                "--output_path", str(m_dir),
                "--output_type", "TXT"
            ]
            conv_proc = subprocess.run(txt_cmd, capture_output=True, text=True)
            if conv_proc.returncode != 0 and not images_txt.exists():
                # Model converter failed to create text files
                pass

        registered_cams = 0
        if images_txt.exists():
            with open(images_txt, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 10 and (parts[9].lower().endswith(".jpg") or parts[9].lower().endswith(".png")):
                            registered_cams += 1

        point_count = 0
        err_sum = 0.0
        track_sum = 0
        if points_txt.exists():
            with open(points_txt, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        point_count += 1
                        # POINT3D_ID X Y Z R G B ERROR (IMAGE_ID POINT2D_IDX)*
                        parts = line.split()
                        if len(parts) >= 8:
                            try:
                                err_sum += float(parts[7])
                                track_sum += (len(parts) - 8) // 2
                            except ValueError:
                                pass

        return {
            "path": m_dir,
            "name": m_dir.name,
            "registered_cams": registered_cams,
            "point_count": point_count,
            "mean_reproj_error_px": round(err_sum / point_count, 3) if point_count else None,
            "mean_track_length": round(track_sum / point_count, 2) if point_count else None,
        }

    @staticmethod
    def qvec2rotmat(qvec: List[float]) -> np.ndarray:
        return np.array([
            [1 - 2 * qvec[2]**2 - 2 * qvec[3]**2,
             2 * qvec[1] * qvec[2] - 2 * qvec[0] * qvec[3],
             2 * qvec[3] * qvec[1] + 2 * qvec[0] * qvec[2]],
            [2 * qvec[1] * qvec[2] + 2 * qvec[0] * qvec[3],
             1 - 2 * qvec[1]**2 - 2 * qvec[3]**2,
             2 * qvec[2] * qvec[3] - 2 * qvec[0] * qvec[1]],
            [2 * qvec[3] * qvec[1] - 2 * qvec[0] * qvec[2],
             2 * qvec[2] * qvec[3] + 2 * qvec[0] * qvec[1],
             1 - 2 * qvec[1]**2 - 2 * qvec[2]**2]
        ])

    @classmethod
    def extract_camera_trajectory(cls, images_txt_path: Path, output_json_path: Path) -> List[Dict[str, Any]]:
        cameras = []
        if not images_txt_path.exists():
            return cameras

        with open(images_txt_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 10 and (parts[9].lower().endswith(".jpg") or parts[9].lower().endswith(".png")):
                    img_id = int(parts[0])
                    qw, qx, qy, qz = map(float, parts[1:5])
                    tx, ty, tz = map(float, parts[5:8])
                    name = parts[9]
                    R = cls.qvec2rotmat([qw, qx, qy, qz])
                    t = np.array([tx, ty, tz])
                    # World position: C = -R^T * t
                    cam_center = -np.dot(R.T, t)
                    # Forward viewing direction: R^T * [0, 0, 1]^T
                    cam_view_dir = R.T[:, 2]
                    cameras.append({
                        "id": img_id,
                        "name": name,
                        "position": [round(float(c), 4) for c in cam_center],
                        "direction": [round(float(d), 4) for d in cam_view_dir],
                        "quaternion": [qw, qx, qy, qz]
                    })

        cameras.sort(key=lambda c: c["name"])
        try:
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(cameras, f, indent=2)
        except Exception:
            pass

        return cameras
