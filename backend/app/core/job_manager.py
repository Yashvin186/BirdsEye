import time
import json
import numpy as np
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from app.config import settings
from app.schemas.pipeline import (
    JobStatusResponse,
    StageDetail,
    StageStatus,
    PipelineConfigRequest
)
from app.services.frame_service import FrameService
from app.services.colmap_service import ColmapService
from app.services.dense_service import DenseService
from app.services.cpu_dense_service import CpuDenseService
from app.services.coverage_service import CoverageService
from app.services.aerial_service import AerialService
from app.services.geo_service import GeoService
from app.services.mesh_service import MeshService
from app.services.report_service import ReportService
from app.core.environment import check_colmap


class JobManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(JobManager, cls).__new__(cls)
                cls._instance._jobs: Dict[str, Dict[str, Any]] = {}
                cls._instance._cancel_flags: Dict[str, bool] = {}
                cls._instance._threads: Dict[str, threading.Thread] = {}
        return cls._instance

    def create_job(self, project_id: str, config: PipelineConfigRequest) -> str:
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        now = datetime.utcnow().isoformat() + "Z"

        all_stage_ids = [
            ("validating", "Video Validation"),
            ("extracting_frames", "Frame Extraction"),
            ("preprocessing", "Quality Filtering & Contact Sheet"),
            ("feature_matching", "COLMAP Feature Detection & Matching"),
            ("sfm", "Structure-from-Motion (SfM)"),
            ("dense_reconstruction", "Dense Stereo Cloud (MVS)"),
            ("ai_depth", "AI Depth Densification (Depth Anything V2)"),
            ("meshing_texturing", "3D Mesh Generation"),
            ("georeferencing_evaluation", "Georeferencing & Evaluation"),
            ("packaging", "Viewer Packaging & Output Verification")
        ]

        stages = [
            StageDetail(stage_id=sid, title=stitle, status=StageStatus.PENDING)
            for sid, stitle in all_stage_ids
        ]

        job_state = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "queued",
            "current_stage": None,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "config": config.model_dump(),
            "stages": [s.model_dump() for s in stages],
            "output_files": {},
            "summary_report": None,
            "warnings": [],
            "error": None,
            "frames_result": {},
            "colmap_result": {},
            "dense_result": {},
            "ai_depth_result": {},
            "mesh_result": {}
        }

        self._jobs[job_id] = job_state
        self._cancel_flags[job_id] = False
        self._persist_job(job_id)
        return job_id

    def get_job(self, job_id: str) -> Optional[JobStatusResponse]:
        state = self._jobs.get(job_id)
        if not state:
            # Try loading from workspace
            for p_dir in settings.BIRDS_EYE_WORKSPACE.iterdir():
                if p_dir.is_dir():
                    j_file = p_dir / "job_state.json"
                    if j_file.exists():
                        try:
                            with open(j_file, "r", encoding="utf-8") as f:
                                saved = json.load(f)
                                if saved.get("job_id") == job_id:
                                    self._jobs[job_id] = saved
                                    state = saved
                                    break
                        except Exception:
                            pass

        if not state:
            return None

        stages_objs = [StageDetail(**s) for s in state["stages"]]
        return JobStatusResponse(
            job_id=state["job_id"],
            project_id=state["project_id"],
            status=state["status"],
            current_stage=state["current_stage"],
            created_at=state["created_at"],
            started_at=state.get("started_at"),
            finished_at=state.get("finished_at"),
            duration_seconds=state.get("duration_seconds"),
            stages=stages_objs,
            output_files=state.get("output_files", {}),
            summary_report=state.get("summary_report"),
            warnings=state.get("warnings", []),
            error=state.get("error")
        )

    def cancel_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            self._cancel_flags[job_id] = True
            self._jobs[job_id]["status"] = "cancelled"
            self._persist_job(job_id)
            return True
        return False

    def is_cancelled(self, job_id: str) -> bool:
        return self._cancel_flags.get(job_id, False)

    def active_job_for_project(self, project_id: str) -> Optional[str]:
        """Job id whose worker thread is still alive for this project (also while a cancel is winding down)."""
        for jid, th in list(self._threads.items()):
            if th.is_alive() and self._jobs.get(jid, {}).get("project_id") == project_id:
                return jid
        return None

    def start_job_thread(self, job_id: str):
        thread = threading.Thread(target=self._run_pipeline, args=(job_id,), daemon=True)
        self._threads[job_id] = thread
        thread.start()

    def _persist_job(self, job_id: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        p_dir = settings.BIRDS_EYE_WORKSPACE / job["project_id"]
        if p_dir.exists():
            try:
                with open(p_dir / "job_state.json", "w", encoding="utf-8") as f:
                    json.dump(job, f, indent=2)
            except Exception:
                pass

    def _update_stage(
        self,
        job_id: str,
        stage_id: str,
        status: StageStatus,
        log_line: Optional[str] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        output_file: Optional[str] = None
    ):
        job = self._jobs[job_id]
        now = datetime.utcnow().isoformat() + "Z"

        for s in job["stages"]:
            if s["stage_id"] == stage_id:
                s["status"] = status.value
                if status == StageStatus.RUNNING and not s.get("started_at"):
                    s["started_at"] = now
                    job["current_stage"] = stage_id
                elif status in (StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED):
                    s["completed_at"] = now

                if log_line:
                    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}][{stage_id}][{status.value}] {log_line}", flush=True)
                    s["log_preview"].append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {log_line}")
                    if len(s["log_preview"]) > 100:
                        s["log_preview"].pop(0)

                if progress is not None:
                    s["progress_percent"] = progress
                if error:
                    s["error_message"] = error
                if output_file and str(output_file) not in s["output_files"]:
                    s["output_files"].append(str(output_file))
                break

        self._persist_job(job_id)

    def _run_pipeline(self, job_id: str):
        job = self._jobs[job_id]
        project_id = job["project_id"]
        project_dir = settings.BIRDS_EYE_WORKSPACE / project_id
        config = PipelineConfigRequest(**job["config"])

        start_time = time.time()
        job["status"] = "running"
        job["started_at"] = datetime.utcnow().isoformat() + "Z"
        self._persist_job(job_id)

        def make_logger(sid):
            return lambda msg: self._update_stage(job_id, sid, StageStatus.RUNNING, log_line=msg)

        try:
            # 1. Validating
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "validating", StageStatus.RUNNING, log_line="Validating project video and metadata...")
            video_meta_file = project_dir / "input" / "video_metadata.json"
            if not video_meta_file.exists():
                raise FileNotFoundError("Video has not been uploaded to this project.")
            with open(video_meta_file, "r", encoding="utf-8") as f:
                video_metadata = json.load(f)
            self._update_stage(job_id, "validating", StageStatus.COMPLETED, log_line=f"Validation passed: {video_metadata['filename']}, {video_metadata['width']}x{video_metadata['height']}")

            # 2 & 3. Extracting Frames and Preprocessing
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "extracting_frames", StageStatus.RUNNING, log_line="Starting frame extraction and decodability validation...")
            self._update_stage(job_id, "preprocessing", StageStatus.RUNNING, log_line="Computing Laplacian sharpness and deduplicating...")

            frames_res = FrameService.extract_and_preprocess(
                project_dir=project_dir,
                config=config,
                log_callback=make_logger("extracting_frames")
            )
            job["frames_result"] = frames_res

            self._update_stage(job_id, "extracting_frames", StageStatus.COMPLETED,
                               log_line=f"Extracted {frames_res['accepted_count']} frames.",
                               output_file=frames_res.get("manifest_json"))
            # Capture QA (post-flight check, per photogrammetry capture guidance) - never blocks the run
            try:
                from app.services.capture_qa_service import CaptureQAService
                job["capture_qa"] = CaptureQAService.analyze(project_dir, frames_res, log=make_logger("preprocessing"))
            except Exception as exc:
                job["capture_qa"] = {"available": False, "reason": str(exc)}
            _qa = job["capture_qa"]
            self._update_stage(job_id, "preprocessing", StageStatus.COMPLETED,
                               log_line=("Capture QA: " + _qa["verdict"].upper() if _qa.get("available") else "Capture QA unavailable") + ". Contact sheet and manifest generated.",
                               output_file=frames_res.get("contact_sheet"))

            # 4. Feature Matching
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "feature_matching", StageStatus.RUNNING, log_line="Checking COLMAP photogrammetry engine & hardware power state...")

            # Hardware acceleration & power detection
            from app.core.environment import get_power_status
            power_info = get_power_status()
            if config.gpu_mode == "cpu":
                use_gpu = False
                gpu_log = "Running in CPU safe mode (battery friendly, no CUDA)."
            elif config.gpu_mode == "cuda":
                use_gpu = True
                gpu_log = "NVIDIA CUDA GPU mode forced by configuration."
            else:  # auto
                if power_info.get("on_battery"):
                    use_gpu = False
                    gpu_log = f"Auto-detected battery power ({power_info.get('battery_percent', 100)}%). Using CPU safe mode to prevent CUDA crashes without charger."
                else:
                    use_gpu = True
                    gpu_log = f"Auto-detected AC charger ({power_info.get('battery_percent', 100)}%). NVIDIA GPU acceleration active."

            self._update_stage(job_id, "feature_matching", StageStatus.RUNNING, log_line=gpu_log)

            colmap_check = check_colmap()
            if not colmap_check.available and ColmapService.use_pycolmap():
                self._update_stage(job_id, "feature_matching", StageStatus.RUNNING,
                                   log_line="COLMAP program not found; using the built-in pycolmap engine for features, matching and SfM.")
            elif not colmap_check.available:
                err_msg = "COLMAP was not found and the pycolmap package is not installed (pip install pycolmap). Feature detection requires one of them."
                self._update_stage(job_id, "feature_matching", StageStatus.FAILED, error=err_msg, log_line=err_msg)
                raise RuntimeError(err_msg)

            self._update_stage(job_id, "feature_matching", StageStatus.RUNNING, log_line="Extracting SIFT features into database.db...")
            fe_res = ColmapService.run_feature_extraction(project_dir, use_gpu=use_gpu, quality_preset=config.quality_preset, log_callback=make_logger("feature_matching"))
            self._update_stage(job_id, "feature_matching", StageStatus.RUNNING, log_line=f"Features extracted into database ({fe_res['database_size_bytes']} bytes). Matching features...")
            ColmapService.run_feature_matching(project_dir, strategy=config.matching_strategy, use_gpu=use_gpu, log_callback=make_logger("feature_matching"))
            self._update_stage(job_id, "feature_matching", StageStatus.COMPLETED, log_line="COLMAP feature extraction and geometric matching succeeded.", output_file=fe_res["database_path"])

            # 5. Structure-from-Motion (SfM)
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "sfm", StageStatus.RUNNING, log_line="Running COLMAP incremental mapper...")
            sfm_res = ColmapService.run_sparse_sfm(project_dir, log_callback=make_logger("sfm"))
            job["colmap_result"] = sfm_res
            # Surface SfM quality problems (low registration, high reprojection error, split models)
            # to the user instead of burying them in the stage log.
            for w in sfm_res.get("warnings", []):
                if w not in job["warnings"]:
                    job["warnings"].append(w)
            # How far around the subject did the camera go? Decides whether a complete 3D model is possible.
            try:
                coverage = CoverageService.analyze(Path(sfm_res["primary_model_path"]))
            except Exception as exc:
                coverage = {"available": False, "reason": str(exc)}
            # Straight-down survey flight over a place (not an object to orbit)? Use the dedicated aerial pipeline.
            survey_mode = False
            try:
                mode = getattr(config, "scene_mode", "auto")
                det = AerialService.detect(Path(sfm_res["primary_model_path"])) if mode != "object" else {"is_aerial": False}
                survey_mode = bool(det.get("is_aerial")) or mode == "aerial"
                if survey_mode:
                    coverage = {
                        "available": True, "verdict": "aerial_survey", "level": "good", "survey_mode": True,
                        "message": ("Aerial survey flight detected (camera looking down over an area). Built a levelled terrain / surface "
                                    "model with a sharp orthomosaic texture from the frames. Only what the camera saw from above is "
                                    "modelled - vertical walls and areas under tree canopy or roofs are not."),
                        "angular_span_deg": 0.0, "sectors_covered": 0, "sectors_total": 0, "coverage_percent": 100.0,
                        "sector_counts": [], "mean_elevation_deg": 90.0, "cameras": int(sfm_res.get("registered_frames", 0)),
                        "detection": det,
                    }
            except Exception as exc:  # detection must never break a job
                survey_mode = False
                print(f"[aerial] detection failed: {exc}", flush=True)
            job["survey_mode"] = survey_mode
            # GPS from the drone's flight log (if provided) -> metres, north orientation, accuracy
            try:
                georef = GeoService.georeference(project_dir, Path(sfm_res["primary_model_path"]), log=make_logger("sfm"))
            except Exception as exc:
                georef = {"status": "alignment_failed", "reason": str(exc)}
            job["georef_result"] = georef
            # Capture planner: tell the pilot exactly which extra pass would fill the missing view
            try:
                if survey_mode:
                    coverage["recommendation"] = ("To also capture building walls, facades and the undersides of trees, add a second pass flown "
                                                  "with the camera tilted ~45 degrees down, flying around or alongside the structures. "
                                                  "A straight-down pass can only ever see roofs and ground.")
                elif coverage.get("available") and coverage.get("level") != "good" and coverage.get("gap_mid_dir_sfm"):
                    where = ""
                    if georef.get("status") == "gps_aligned":
                        d = np.array(coverage["gap_mid_dir_sfm"])
                        bearing = float(np.degrees(np.arctan2(d @ np.array(georef["east_sfm"]), d @ np.array(georef["north_sfm"]))) % 360.0)
                        names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
                        where = f" on the {names[int((bearing + 22.5) // 45) % 8]} side (compass bearing about {bearing:.0f} degrees from the subject)"
                        coverage["gap_bearing_deg"] = round(bearing, 0)
                    coverage["recommendation"] = (f"Fly one more pass{where} covering about {coverage['gap_deg']:.0f} degrees of the missing arc: "
                                                  "same distance, camera aimed at the subject, ~45 degrees down, slow and steady.")
            except Exception as exc:
                print(f"[coverage] planner failed: {exc}", flush=True)
            job["coverage_result"] = coverage
            if coverage.get("available") and coverage.get("level") != "good" and coverage["message"] not in job["warnings"]:
                job["warnings"].append(coverage["message"])
            self._update_stage(job_id, "sfm", StageStatus.COMPLETED,
                               log_line=(coverage["message"] if survey_mode else
                                         f"Viewpoint coverage: {coverage['angular_span_deg']:.0f} degrees around the subject "
                                         f"({coverage['sectors_covered']}/{coverage['sectors_total']} sectors). {coverage['message']}")
                               if coverage.get("available") else "Viewpoint coverage could not be measured.")
            self._update_stage(job_id, "sfm", StageStatus.COMPLETED,
                               log_line=f"SfM reconstructed {sfm_res['point_count']} points with {sfm_res['registered_frames']} registered images.",
                               output_file=sfm_res["sparse_ply"])
            if sfm_res.get("cameras_json"):
                self._update_stage(job_id, "sfm", StageStatus.COMPLETED, output_file=sfm_res["cameras_json"])

            # 6. Dense Reconstruction (MVS)
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "dense_reconstruction", StageStatus.RUNNING, log_line="Evaluating dense stereo capabilities...")
            dense_res = {"status": "skipped", "reason": "Disabled in configuration"}
            if survey_mode:
                dense_res = {"status": "skipped", "reason": "Aerial survey mode: terrain surface is built from the SfM points and frames."}
                self._update_stage(job_id, "dense_reconstruction", StageStatus.SKIPPED,
                                   log_line="Aerial survey mode - object-style dense stereo is not needed; building the terrain model directly.")
            elif config.enable_dense_mvs:
                dense_res = DenseService.run_dense_reconstruction(
                    project_dir=project_dir,
                    primary_sparse_model=Path(sfm_res["primary_model_path"]),
                    use_gpu=use_gpu,
                    isolate_subject=config.isolate_subject,
                    quality_preset=config.quality_preset,
                    log_callback=make_logger("dense_reconstruction")
                )
                if dense_res["status"] in ("unsupported", "skipped", "failed") and config.cpu_stereo_fallback:
                    # No CUDA/MVS: fall back to CPU stereo so the user still gets a dense surface
                    # instead of a bare sparse cloud.
                    dlog = make_logger("dense_reconstruction")
                    dlog(f"MVS unavailable ({dense_res.get('reason')}). Trying CPU stereo fallback (OpenCV SGBM)...")
                    try:
                        cpu_res = CpuDenseService.run(
                            project_dir=project_dir,
                            primary_sparse_model=Path(sfm_res["primary_model_path"]),
                            quality_preset=config.quality_preset,
                            log_callback=dlog,
                        )
                        if cpu_res["status"] == "completed":
                            post = DenseService.postprocess_cloud(
                                Path(cpu_res["dense_ply"]), Path(sfm_res["primary_model_path"]),
                                project_dir / "outputs", isolate_subject=False, log_callback=dlog)
                            dense_res = {
                                "status": "completed", "reason": None, "method": "cpu_stereo_sgbm",
                                "dense_ply": str(post["path"]), "dense_point_count": post["point_count"],
                                "subject_isolation": cpu_res.get("subject_isolation"),
                                "pairs_used": cpu_res.get("pairs_used"),
                                "multi_view_confirmed": cpu_res.get("multi_view_confirmed"),
                            }
                        else:
                            dlog(f"[NOTICE] CPU stereo fallback produced no cloud: {cpu_res.get('reason')}")
                    except Exception as exc:  # fallback must never break the job
                        dlog(f"[NOTICE] CPU stereo fallback failed: {exc}")
                job["dense_result"] = dense_res
                if dense_res["status"] == "completed":
                    self._update_stage(job_id, "dense_reconstruction", StageStatus.COMPLETED,
                                       log_line=f"Dense point cloud fused ({dense_res['dense_point_count']} points).",
                                       output_file=dense_res.get("dense_ply"))
                elif dense_res["status"] == "unsupported":
                    self._update_stage(job_id, "dense_reconstruction", StageStatus.UNSUPPORTED,
                                       log_line=f"Dense MVS unsupported: {dense_res['reason']}")
                elif dense_res["status"] == "failed":
                    self._update_stage(job_id, "dense_reconstruction", StageStatus.FAILED,
                                       error=dense_res["reason"],
                                       log_line=f"Dense MVS failed: {dense_res['reason']}")
                else:
                    self._update_stage(job_id, "dense_reconstruction", StageStatus.SKIPPED,
                                       log_line=f"Dense MVS skipped: {dense_res.get('reason')}")
            else:
                self._update_stage(job_id, "dense_reconstruction", StageStatus.SKIPPED, log_line="Dense reconstruction disabled in configuration.")

            # 6b. AI Depth Estimation & Densification (Depth Anything V2)
            if self.is_cancelled(job_id): return
            ai_depth_res = {"status": "skipped", "reason": "Disabled in configuration"}
            if survey_mode:
                self._update_stage(job_id, "ai_depth", StageStatus.SKIPPED, log_line="Aerial survey mode - monocular depth not used (measured geometry only).")
            elif config.enable_ai_depth:
                self._update_stage(job_id, "ai_depth", StageStatus.RUNNING, log_line="Running Depth Anything V2 monocular depth densification...")
                try:
                    from app.services.ai_depth_service import AiDepthService
                    primary_sparse = Path(sfm_res["primary_model_path"]) if sfm_res.get("primary_model_path") else None
                    ai_depth_res = AiDepthService.run_ai_densification(
                        project_dir=project_dir,
                        primary_sparse_dir=primary_sparse,
                        quality_preset=config.quality_preset,
                        log_callback=make_logger("ai_depth")
                    )
                    job["ai_depth_result"] = ai_depth_res
                    if ai_depth_res.get("status") == "completed":
                        self._update_stage(
                            job_id, "ai_depth", StageStatus.COMPLETED,
                            log_line=f"AI surface densification completed: {ai_depth_res.get('total_points', 0):,} total points.",
                            output_file=ai_depth_res.get("fused_cloud_ply")
                        )
                    else:
                        self._update_stage(
                            job_id, "ai_depth", StageStatus.PARTIAL,
                            log_line=f"AI densification partial: {ai_depth_res.get('reason')}"
                        )
                except Exception as e:
                    self._update_stage(
                        job_id, "ai_depth", StageStatus.FAILED,
                        error=str(e),
                        log_line=f"AI densification failed: {e}"
                    )
            else:
                self._update_stage(job_id, "ai_depth", StageStatus.SKIPPED, log_line="AI depth densification disabled in configuration.")

            # 7. Meshing and Texturing
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "meshing_texturing", StageStatus.RUNNING, log_line="Reconstructing 3D surface mesh from photogrammetric model...")
            mesh_res = {"status": "skipped", "reason": "Disabled in configuration"}
            if config.enable_meshing and survey_mode:
                mlog = make_logger("meshing_texturing")
                try:
                    mesh_res = AerialService.build(project_dir, Path(sfm_res["primary_model_path"]), georef=job.get("georef_result"), log=mlog)
                except Exception as exc:
                    mesh_res = {"status": "failed", "reason": f"aerial terrain model failed: {exc}"}
                job["mesh_result"] = mesh_res
                if mesh_res.get("status") == "completed":
                    self._update_stage(job_id, "meshing_texturing", StageStatus.COMPLETED,
                                       log_line=f"Textured terrain model: {mesh_res['vertex_count']} vertices, {mesh_res['face_count']} faces, orthomosaic {mesh_res['texture_size'][0]}x{mesh_res['texture_size'][1]}px.",
                                       output_file=mesh_res["obj_path"])
                    for key in ("glb_path", "mesh_ply_path", "orthomosaic_path", "dsm_path"):
                        if mesh_res.get(key):
                            self._update_stage(job_id, "meshing_texturing", StageStatus.COMPLETED, output_file=mesh_res[key])
                else:
                    self._update_stage(job_id, "meshing_texturing", StageStatus.FAILED, error=mesh_res.get("reason"),
                                       log_line=f"Surface meshing failed: {mesh_res.get('reason')}")
            elif config.enable_meshing:
                # Use best available dense cloud (AI fused cloud, filtered MVS cloud, or sparse cloud fallback)
                fused_ai_path = project_dir / "outputs" / "dense_cloud_fused_ai.ply"
                ai_only_path = project_dir / "outputs" / "dense_cloud_ai.ply"
                if ai_depth_res.get("status") == "completed" and fused_ai_path.exists():
                    preferred_cloud = fused_ai_path
                elif ai_depth_res.get("status") == "completed" and ai_only_path.exists():
                    preferred_cloud = ai_only_path
                elif dense_res.get("status") == "completed" and dense_res.get("dense_ply"):
                    preferred_cloud = Path(dense_res["dense_ply"])
                else:
                    preferred_cloud = Path(sfm_res["sparse_ply"])

                mesh_res = MeshService.generate_mesh_from_point_cloud(
                    project_dir=project_dir,
                    primary_sparse_model=Path(sfm_res["primary_model_path"]),
                    preferred_cloud_path=preferred_cloud,
                    fill_unseen_regions=config.fill_unseen_regions,
                    quality_preset=config.quality_preset,
                    log_callback=make_logger("meshing_texturing")
                )
                job["mesh_result"] = mesh_res
                if mesh_res.get("status") == "completed":
                    self._update_stage(job_id, "meshing_texturing", StageStatus.COMPLETED,
                                       log_line=f"Surface mesh reconstructed: {mesh_res['vertex_count']} vertices, {mesh_res['face_count']} faces.",
                                       output_file=mesh_res["obj_path"])
                    if mesh_res.get("glb_path"):
                        self._update_stage(job_id, "meshing_texturing", StageStatus.COMPLETED, output_file=mesh_res["glb_path"])
                    if mesh_res.get("mesh_ply_path"):
                        self._update_stage(job_id, "meshing_texturing", StageStatus.COMPLETED, output_file=mesh_res["mesh_ply_path"])
                else:
                    self._update_stage(job_id, "meshing_texturing", StageStatus.FAILED,
                                       error=mesh_res.get("reason"),
                                       log_line=f"Surface meshing failed: {mesh_res.get('reason')}")
            else:
                self._update_stage(job_id, "meshing_texturing", StageStatus.SKIPPED, log_line="Surface meshing disabled in configuration.")

            # 8. Georeferencing and Evaluation
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "georeferencing_evaluation", StageStatus.RUNNING, log_line="Evaluating scale, registration metrics, and limitations...")
            quality_report = ReportService.generate_quality_report(
                project_dir=project_dir,
                job_data=job,
                video_metadata=video_metadata
            )
            job["summary_report"] = quality_report
            self._update_stage(job_id, "georeferencing_evaluation", StageStatus.COMPLETED,
                               log_line=f"Quality report generated: Scale status = {quality_report['georeferencing']['status']}",
                               output_file=str(project_dir / "outputs" / "quality_report.json"))

            # 9. Packaging
            if self.is_cancelled(job_id): return
            self._update_stage(job_id, "packaging", StageStatus.RUNNING, log_line="Verifying final output files and packaging exports...")
            outputs_dir = project_dir / "outputs"
            try:
                from app.services.delivery_service import DeliveryService
                job["delivery"] = DeliveryService.build(project_dir, job, log=make_logger("packaging"))
                job["output_qa"] = (job["delivery"] or {}).get("output_qa")
            except Exception as exc:
                job["delivery"] = {"available": False, "reason": str(exc)}
            verified_files = {}
            for item in outputs_dir.iterdir():
                if item.is_file() and item.stat().st_size > 0:
                    verified_files[item.name] = {
                        "name": item.name,
                        "size_bytes": item.stat().st_size,
                        "format": item.suffix.lstrip(".").upper()
                    }
            job["output_files"] = verified_files
            self._update_stage(job_id, "packaging", StageStatus.COMPLETED, log_line=f"Packaging complete. {len(verified_files)} verified output files.")

            # Honest final job status determination:
            # - "completed": All enabled stages (SfM, dense MVS, mesh) succeeded
            # - "partial": SfM succeeded with valid point cloud, but dense MVS or meshing failed/unsupported
            has_sparse = bool(sfm_res and sfm_res.get("point_count", 0) > 0)
            dense_ok = survey_mode or (not config.enable_dense_mvs) or (dense_res.get("status") == "completed")
            mesh_ok = (not config.enable_meshing) or (mesh_res.get("status") == "completed")

            if has_sparse and dense_ok and mesh_ok:
                final_status = "completed"
            elif has_sparse:
                final_status = "partial"
            else:
                final_status = "failed"

            job["status"] = final_status
            job["current_stage"] = "completed"
            job["finished_at"] = datetime.utcnow().isoformat() + "Z"
            job["duration_seconds"] = round(time.time() - start_time, 2)
            self._persist_job(job_id)

            p_file = project_dir / "project.json"
            if p_file.exists():
                try:
                    with open(p_file, "r+", encoding="utf-8") as pf:
                        p_data = json.load(pf)
                        p_data["status"] = final_status
                        p_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
                        pf.seek(0)
                        json.dump(p_data, pf, indent=2)
                        pf.truncate()
                except Exception:
                    pass

        except Exception as e:
            curr_sid = job.get("current_stage") or "validating"
            self._update_stage(job_id, curr_sid, StageStatus.FAILED, error=str(e), log_line=f"Error: {str(e)}")
            job["status"] = "failed"
            job["error"] = str(e)
            job["finished_at"] = datetime.utcnow().isoformat() + "Z"
            job["duration_seconds"] = round(time.time() - start_time, 2)
            self._persist_job(job_id)

            p_file = project_dir / "project.json"
            if p_file.exists():
                try:
                    with open(p_file, "r+", encoding="utf-8") as pf:
                        p_data = json.load(pf)
                        p_data["status"] = "failed"
                        p_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
                        pf.seek(0)
                        json.dump(p_data, pf, indent=2)
                        pf.truncate()
                except Exception:
                    pass


job_manager = JobManager()
