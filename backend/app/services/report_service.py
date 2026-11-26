import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ReportService:
    @classmethod
    def generate_quality_report(
        cls,
        project_dir: Path,
        job_data: Dict[str, Any],
        video_metadata: Optional[Dict[str, Any]] = None,
        flight_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        outputs_dir = project_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        frames_data = job_data.get("frames_result", {})
        colmap_data = job_data.get("colmap_result", {})
        dense_data = job_data.get("dense_result", {})
        mesh_data = job_data.get("mesh_result", {})

        has_gcp = bool(flight_params and flight_params.get("gcp_points"))
        has_gps = bool(video_metadata and video_metadata.get("has_gps"))
        has_scale_ref = bool(flight_params and flight_params.get("known_scale_distance_m"))

        if has_gcp or (has_gps and has_scale_ref):
            geo_status = "Georeferenced / Calibrated"
            scale_note = f"Metric scale derived from {'GCPs' if has_gcp else 'GPS and reference distance'}."
        else:
            geo_status = "Unknown Absolute Scale (Relative Coordinates Only)"
            scale_note = "Single-pass continuous drone video without validated GCPs or ground scale references. Measurements in the viewer represent arbitrary model units."

        geo = job_data.get("georef_result") or {}
        mesh_geo = (job_data.get("mesh_result") or {})
        if geo.get("status") == "gps_aligned":
            geo_status = "GPS-scaled (metres)"
            scale_note = (f"Scale derived from the drone's GPS log ({geo['source']}): 1 model unit = {geo['metres_per_unit']:.3f} m, "
                          f"camera-path residual {geo['rmse_m']:.1f} m (RMSE) over {geo['inlier_cameras']}/{geo['cameras_used']} frames. "
                          "Distances are metric to within the GPS accuracy of the flight (typically a few percent); absolute position is only as good as "
                          "consumer GPS (a few metres) and heights are the least reliable axis. Not survey-grade without ground control points.")
        elif geo.get("reason"):
            scale_note += f" (GPS scaling not applied: {geo['reason']})"

        coverage = job_data.get("coverage_result") or {}
        report = {
            "coverage": coverage,
            "capture_qa": job_data.get("capture_qa") or {},
            "output_qa": job_data.get("output_qa") or {},
            "project_id": project_dir.name,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "pipeline_status": "completed" if job_data.get("status") in ("running", "queued", None) else job_data.get("status", "unknown"),  # the report is written by the last stage, just before the job is marked completed
            "video_input": {
                "filename": video_metadata.get("original_filename") if video_metadata else "unknown",
                "duration_seconds": video_metadata.get("duration_seconds") if video_metadata else None,
                "fps": video_metadata.get("fps") if video_metadata else None,
                "resolution": f"{video_metadata.get('width')}x{video_metadata.get('height')}" if video_metadata else "unknown",
                "codec": video_metadata.get("codec") if video_metadata else "unknown"
            },
            "frame_extraction": {
                "candidates_evaluated": frames_data.get("candidates_evaluated", 0),
                "accepted_frames": frames_data.get("accepted_count", 0),
                "rejected_frames": frames_data.get("rejected_count", 0),
            },
            "sparse_sfm": {
                "points_count": colmap_data.get("point_count", 0),
                "registered_frames": colmap_data.get("registered_frames", 0),
                "registration_percentage": colmap_data.get("registration_percent", 0.0),
                "submodels_count": colmap_data.get("submodels_count", 1),
                "mean_reprojection_error_px": colmap_data.get("mean_reproj_error_px"),
                "mean_track_length": colmap_data.get("mean_track_length"),
                "warnings": colmap_data.get("warnings", [])
            },
            "dense_mvs": {
                "status": dense_data.get("status", "not_run"),
                "dense_points_count": dense_data.get("dense_point_count", 0),
                "skip_reason": dense_data.get("reason"),
                "method": dense_data.get("method", "colmap_patch_match_stereo" if dense_data.get("status") == "completed" else None),
                "subject_isolation": dense_data.get("subject_isolation")
            },
            "mesh": {
                "status": mesh_data.get("status", "skipped" if not mesh_data else "completed"),
                "texture_type": mesh_data.get("texture_type", "vertex_color" if mesh_data.get("vertex_count", 0) > 0 else "none"),
                "source_cloud_type": mesh_data.get("source_cloud_type", "sparse_sfm"),
                "method": mesh_data.get("mesh_method"),
                # "left_empty": regions the video never saw have no surface (honest).
                # "extrapolated": a closed surface was invented over them (approximate, not measured).
                "unseen_regions": mesh_data.get("unseen_regions"),
                "vertex_count": mesh_data.get("vertex_count", 0),
                "face_count": mesh_data.get("face_count", 0),
                "dimensions": mesh_data.get("dimensions", [])
            },
            "georeferencing": {
                "status": geo_status,
                "notes": scale_note,
                "survey_grade": False,
                "rmse_error": geo.get("rmse_m") if geo.get("status") == "gps_aligned" else None,  # camera-path residual vs GPS, not a ground-truth accuracy
                "metres_per_unit": geo.get("metres_per_unit") if geo.get("status") == "gps_aligned" else None,
                "metres_per_scene_unit": mesh_geo.get("metres_per_scene_unit") if geo.get("status") == "gps_aligned" else None,
                "vertical_exaggeration": mesh_geo.get("vertical_exaggeration", 1.0),
                "origin": geo.get("origin") if geo.get("status") == "gps_aligned" else None,
                "ground_size_m": mesh_geo.get("ground_size_m"),
                "ground_sample_distance_cm": mesh_geo.get("gsd_cm"),
                "survey_area_m2": (round(mesh_geo["ground_size_m"][0] * mesh_geo["ground_size_m"][1], 0) if isinstance(mesh_geo.get("ground_size_m"), (list, tuple)) and len(mesh_geo["ground_size_m"]) >= 2 else None),
            },
            "limitations_and_disclaimers": [
                "Reconstruction was obtained from a single-pass continuous drone video.",
                "Surface geometry in shadowed, occluded, or featureless areas may be incomplete.",
                "Without ground control points (GCPs), absolute scale and coordinates cannot be guaranteed for civil surveying."
            ]
        }
        if coverage.get("available") and coverage.get("level") != "good":
            report["limitations_and_disclaimers"].insert(0, coverage["message"])
        cqa = job_data.get("capture_qa") or {}
        if cqa.get("available") and cqa.get("verdict") != "good":
            for line in cqa.get("issues", []) + cqa.get("advice", []):
                report["limitations_and_disclaimers"].append("Capture: " + line)
        oqa = job_data.get("output_qa") or {}
        if oqa.get("available") and oqa.get("issues"):
            for line in oqa["issues"]:
                report["limitations_and_disclaimers"].append("Output check: " + line)
        if coverage.get("recommendation"):
            report["limitations_and_disclaimers"].append("Capture advice: " + coverage["recommendation"])
        if mesh_data.get("unseen_regions") == "extrapolated":
            report["limitations_and_disclaimers"].append(
                "Surfaces over regions the video never observed were EXTRAPOLATED by Poisson reconstruction. "
                "They make the model look complete but are not measured geometry."
            )
        elif mesh_data.get("status") == "completed":
            report["limitations_and_disclaimers"].append(
                "Regions the video never observed (undersides, hidden sides) are intentionally left empty rather than invented. "
                "Capture them with additional passes from other angles."
            )

        # Save JSON
        json_path = outputs_dir / "quality_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        # Save Markdown
        md_path = outputs_dir / "quality_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Birds Eye 3D Reconstruction Quality Report\n\n")
            f.write(f"- **Project ID:** `{report['project_id']}`\n")
            f.write(f"- **Generated At:** {report['generated_at']}\n")
            f.write(f"- **Pipeline Status:** {report['pipeline_status']}\n\n")
            f.write(f"## 1. Video Intake & Keyframes\n")
            f.write(f"- Resolution: {report['video_input']['resolution']}\n")
            f.write(f"- Candidate frames evaluated: {report['frame_extraction']['candidates_evaluated']}\n")
            f.write(f"- Accepted frames: {report['frame_extraction']['accepted_frames']} ({report['frame_extraction']['rejected_frames']} filtered for blur/duplicates)\n\n")
            f.write(f"## 2. Photogrammetry (COLMAP SfM & Dense MVS)\n")
            f.write(f"- Sparse 3D points: {report['sparse_sfm']['points_count']:,}\n")
            f.write(f"- Registered cameras: {report['sparse_sfm']['registered_frames']} ({report['sparse_sfm']['registration_percentage']}%)\n")
            f.write(f"- Dense MVS status: {report['dense_mvs']['status']} ({report['dense_mvs']['dense_points_count']:,} dense points)\n")
            iso = report['dense_mvs'].get('subject_isolation') or {}
            if report['dense_mvs'].get('method') == "cpu_stereo_sgbm":
                f.write("  - Method: CPU stereo (OpenCV SGBM). Noisier than GPU MVS; short baselines limit depth accuracy.\n")
            if iso.get('applied'):
                f.write(f"  - Subject isolation: kept {iso.get('kept_points', 0) / max(iso.get('total_points', 1), 1) * 100:.0f}% of dense points; "
                        f"distant background (unreliable depth) was removed.\n")
            elif iso.get('matched_total'):
                f.write(f"  - Subject isolation: {iso.get('in_volume_total', 0) / max(iso.get('matched_total', 1), 1) * 100:.0f}% of stereo matches lay inside the SfM-verified volume; the rest (distant background) were discarded.\n")
            if report['dense_mvs']['skip_reason']:
                f.write(f"  - Note: {report['dense_mvs']['skip_reason']}\n")
            f.write(f"\n## 3. Surface Mesh\n")
            f.write(f"- Vertices: {report['mesh']['vertex_count']:,}\n")
            f.write(f"- Triangles: {report['mesh']['face_count']:,}\n\n")
            f.write(f"## 4. Georeferencing & Scale Integrity\n")
            f.write(f"- **Status:** {report['georeferencing']['status']}\n")
            f.write(f"- **Notice:** {report['georeferencing']['notes']}\n\n")
            if coverage.get("available") and coverage.get("verdict") == "aerial_survey":
                f.write(f"## Scene type\n- Aerial survey (nadir flight). {coverage['message']}\n\n")
            elif coverage.get("available"):
                f.write(f"## Viewpoint coverage\n- Angular span around the subject: {coverage['angular_span_deg']:.0f} degrees "
                        f"({coverage['sectors_covered']}/{coverage['sectors_total']} sectors of 30 degrees)\n- {coverage['message']}\n\n")
            f.write(f"## 5. Limitations\n")
            for lim in report['limitations_and_disclaimers']:
                f.write(f"- {lim}\n")

        return report
