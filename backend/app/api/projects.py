import json
import uuid
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, status

from app.config import settings
from app.schemas.project import ProjectCreateRequest, ProjectSummary, VideoMetadata
from app.schemas.pipeline import PipelineConfigRequest
from app.services.video_service import VideoService
from app.services.geo_service import GeoService
from app.services.image_sequence_service import ImageSequenceService
from pydantic import BaseModel
from app.core.job_manager import job_manager

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.post("", response_model=ProjectSummary)
def create_project(req: ProjectCreateRequest):
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    project_dir = settings.BIRDS_EYE_WORKSPACE / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow().isoformat() + "Z"
    meta = {
        "id": project_id,
        "name": req.name,
        "description": req.description or "",
        "created_at": now,
        "updated_at": now,
        "status": "created",
        "flight_params": req.flight_params.model_dump() if req.flight_params else None
    }

    with open(project_dir / "project.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return ProjectSummary(
        id=project_id,
        name=req.name,
        description=req.description,
        created_at=now,
        updated_at=now,
        status="created",
        video_uploaded=False,
        video_metadata=None,
        has_results=False,
        output_files_count=0
    )


@router.get("", response_model=List[ProjectSummary])
def list_projects():
    projects = []
    if not settings.BIRDS_EYE_WORKSPACE.exists():
        return []

    for p_dir in settings.BIRDS_EYE_WORKSPACE.iterdir():
        if p_dir.is_dir():
            p_file = p_dir / "project.json"
            if p_file.exists():
                try:
                    with open(p_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    video_meta = None
                    vm_file = p_dir / "input" / "video_metadata.json"
                    if vm_file.exists():
                        with open(vm_file, "r", encoding="utf-8") as vmf:
                            video_meta = VideoMetadata(**json.load(vmf))

                    outputs_dir = p_dir / "outputs"
                    output_files = [f for f in outputs_dir.iterdir() if f.is_file()] if outputs_dir.exists() else []

                    project_status = data.get("status", "created")
                    j_file = p_dir / "job_state.json"
                    if j_file.exists():
                        try:
                            with open(j_file, "r", encoding="utf-8") as jf:
                                j_state = json.load(jf)
                                if j_state.get("status") in ("completed", "failed", "partial"):
                                    project_status = j_state["status"]
                        except Exception:
                            pass

                    projects.append(ProjectSummary(
                        id=data["id"],
                        name=data["name"],
                        description=data.get("description"),
                        created_at=data["created_at"],
                        updated_at=data.get("updated_at", data["created_at"]),
                        status=project_status,
                        video_uploaded=(video_meta is not None),
                        video_metadata=video_meta,
                        has_results=(len(output_files) > 0),
                        output_files_count=len(output_files)
                    ))
                except Exception:
                    continue

    projects.sort(key=lambda p: p.created_at, reverse=True)
    return projects


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: str):
    project_dir = VideoService.get_project_dir(project_id)
    p_file = project_dir / "project.json"
    if not p_file.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    with open(p_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    video_meta = None
    vm_file = project_dir / "input" / "video_metadata.json"
    if vm_file.exists():
        with open(vm_file, "r", encoding="utf-8") as vmf:
            video_meta = VideoMetadata(**json.load(vmf))

    outputs_dir = project_dir / "outputs"
    output_files = [f for f in outputs_dir.iterdir() if f.is_file()] if outputs_dir.exists() else []

    project_status = data.get("status", "created")
    j_file = project_dir / "job_state.json"
    if j_file.exists():
        try:
            with open(j_file, "r", encoding="utf-8") as jf:
                j_state = json.load(jf)
                if j_state.get("status") in ("completed", "failed", "partial"):
                    project_status = j_state["status"]
        except Exception:
            pass

    return ProjectSummary(
        id=data["id"],
        name=data["name"],
        description=data.get("description"),
        created_at=data["created_at"],
        updated_at=data.get("updated_at", data["created_at"]),
        status=project_status,
        video_uploaded=(video_meta is not None),
        video_metadata=video_meta,
        has_results=(len(output_files) > 0),
        output_files_count=len(output_files)
    )


@router.get("/{project_id}/job")
def get_project_latest_job(project_id: str):
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    j_file = project_dir / "job_state.json"
    if j_file.exists():
        try:
            with open(j_file, "r", encoding="utf-8") as jf:
                saved = json.load(jf)
                job_id = saved.get("job_id")
                if job_id:
                    job = job_manager.get_job(job_id)
                    if job:
                        return job
        except Exception:
            pass

    return None


@router.post("/{project_id}/video", response_model=VideoMetadata)
async def upload_video(project_id: str, file: UploadFile = File(...)):
    # Validate project exists
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    if job_manager.active_job_for_project(project_id):
        raise HTTPException(status_code=409, detail="A reconstruction job is still running for this project.")

    (project_dir / "input" / "image_sequence.json").unlink(missing_ok=True)   # a real video replaces any imported frames
    # Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in [".mp4", ".mov", ".avi", ".mkv"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported video file extension: '{ext}'. Please upload an MP4 or MOV video."
        )

    # Save to temp file first to stream and check size
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp_path = Path(tmp.name)
        try:
            chunk_size = 1024 * 1024 * 4  # 4MB chunks
            while chunk := await file.read(chunk_size):
                tmp.write(chunk)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Failed to stream upload: {e}")

    try:
        metadata = VideoService.inspect_and_save(
            project_id=project_id,
            uploaded_file_path=tmp_path,
            original_filename=file.filename or "video.mp4"
        )
        # Update project status
        p_file = project_dir / "project.json"
        if p_file.exists():
            with open(p_file, "r+", encoding="utf-8") as pf:
                p_data = json.load(pf)
                p_data["status"] = "video_uploaded"
                p_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
                pf.seek(0)
                json.dump(p_data, pf, indent=2)
                pf.truncate()

        return metadata
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    finally:
        tmp_path.unlink(missing_ok=True)




class ImportFolderRequest(BaseModel):
    path: str
    max_images: int = 200


@router.post("/{project_id}/import_folder", response_model=VideoMetadata)
def import_image_folder(project_id: str, req: ImportFolderRequest):
    """Use a folder of frames (jpg/png) on this machine as the input, instead of a video file."""
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    if job_manager.active_job_for_project(project_id):
        raise HTTPException(status_code=409, detail="A reconstruction job is still running for this project.")
    try:
        info = ImageSequenceService.import_folder(project_dir, req.path, req.max_images, ffmpeg=settings.FFMPEG_EXE if settings.FFMPEG_EXE and Path(settings.FFMPEG_EXE).exists() else "ffmpeg")
        meta = VideoService.inspect_and_save(project_id=project_id, uploaded_file_path=info["tmp_video"], original_filename="image_sequence.mp4")
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    meta.warnings = [w for w in meta.warnings if "frame rate" not in w and "duration" not in w.lower()]
    if info["images_found"] > info["images_used"]:
        meta.warnings.append(f"Folder has {info['images_found']} images; {info['images_used']} evenly spaced ones are used to keep processing time reasonable (raise 'max images' for more detail).")
    if info.get("exif_gps"):
        meta.warnings.append(f"GPS found in the photos' EXIF ({info['images_with_gps']} images): the model will be scaled to real metres automatically.")
    else:
        meta.warnings.append("No GPS in these images, so the model is in relative units. After reconstruction, measure one known length in the 3D viewer and press 'Set scale' to get real metres.")
    p_file = project_dir / "project.json"
    if p_file.exists():
        d = json.loads(p_file.read_text(encoding="utf-8")); d["status"] = "video_uploaded"; d["updated_at"] = datetime.utcnow().isoformat() + "Z"
        p_file.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return meta

@router.post("/{project_id}/telemetry")
async def upload_telemetry(project_id: str, file: UploadFile = File(...)):
    """Optional drone flight log (.SRT written next to the video by DJI and similar drones). Gives real-metre scale."""
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    if job_manager.active_job_for_project(project_id):
        raise HTTPException(status_code=409, detail="A reconstruction job is still running for this project.")
    if Path(file.filename or "").suffix.lower() != ".srt":
        raise HTTPException(status_code=400, detail="Telemetry must be the drone's .SRT subtitle file (same name as the video).")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Telemetry file is unexpectedly large (>20 MB).")
    in_dir = project_dir / "input"
    in_dir.mkdir(parents=True, exist_ok=True)
    tmp = in_dir / "telemetry.srt.tmp"
    tmp.write_bytes(data)
    try:
        samples = GeoService.parse_srt(tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not read the SRT file: {exc}")
    if len(samples) < 3:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="No GPS samples found. Expected lines like '[latitude: 12.34] [longitude: 77.56] [rel_alt: 40.0]'.")
    for old in in_dir.glob("*.srt"):
        old.unlink(missing_ok=True)
    tmp.replace(in_dir / "telemetry.srt")
    return {"filename": file.filename, "samples": len(samples), "duration_s": round(samples[-1]["t"] - samples[0]["t"], 1),
            "start": {"lat": samples[0]["lat"], "lon": samples[0]["lon"]}}

@router.get("/samples/list")
def list_sample_videos():
    ref_dir = settings.BIRDS_EYE_WORKSPACE.parent / "reference"
    samples = []
    if ref_dir.exists():
        for f in ref_dir.glob("*.mp4"):
            samples.append({
                "name": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 1)
            })
    return samples


@router.post("/{project_id}/load_sample", response_model=VideoMetadata)
def load_sample_video(project_id: str, sample_name: str = "some.mp4"):
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    ref_dir = settings.BIRDS_EYE_WORKSPACE.parent / "reference"
    if job_manager.active_job_for_project(project_id):
        raise HTTPException(status_code=409, detail="A reconstruction job is still running for this project.")
    # Only the bare file name is honoured, so "../" cannot reach files outside the reference folder,
    # and a missing sample is an error rather than silently loading some other video.
    target_sample = ref_dir / Path(sample_name).name
    if not target_sample.exists() or not target_sample.is_file():
        raise HTTPException(status_code=404, detail=f"Sample video '{Path(sample_name).name}' not found in reference directory.")

    (VideoService.get_project_dir(project_id) / "input" / "image_sequence.json").unlink(missing_ok=True)
    metadata = VideoService.inspect_and_save(
        project_id=project_id,
        uploaded_file_path=target_sample,
        original_filename=target_sample.name
    )
    # A sample can ship with its drone flight log (same name, .SRT) -> real-metre scale
    (project_dir / "input").mkdir(parents=True, exist_ok=True)
    for old in (project_dir / "input").glob("*.srt"):
        old.unlink(missing_ok=True)
    sidecar = next((c for c in target_sample.parent.glob(target_sample.stem + ".*") if c.suffix.lower() == ".srt"), None)
    if sidecar:
        shutil.copy2(sidecar, project_dir / "input" / "telemetry.srt")

    # Update project status
    p_file = project_dir / "project.json"
    if p_file.exists():
        with open(p_file, "r+", encoding="utf-8") as pf:
            p_data = json.load(pf)
            p_data["status"] = "video_uploaded"
            p_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
            pf.seek(0)
            json.dump(p_data, pf, indent=2)
            pf.truncate()

    return metadata


@router.post("/{project_id}/reconstruction")
def start_reconstruction(project_id: str, config: Optional[PipelineConfigRequest] = None):
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    video_meta = project_dir / "input" / "video_metadata.json"
    if not video_meta.exists():
        raise HTTPException(status_code=400, detail="Cannot start reconstruction: No video has been uploaded yet.")

    running = job_manager.active_job_for_project(project_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A reconstruction job ({running}) is still running for this project. Wait for it to finish or cancel it first."
        )

    cfg = config or PipelineConfigRequest()
    job_id = job_manager.create_job(project_id=project_id, config=cfg)
    job_manager.start_job_thread(job_id)

    # Update project status
    p_file = project_dir / "project.json"
    if p_file.exists():
        with open(p_file, "r+", encoding="utf-8") as pf:
            p_data = json.load(pf)
            p_data["status"] = "processing"
            p_data["current_job_id"] = job_id
            p_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
            pf.seek(0)
            json.dump(p_data, pf, indent=2)
            pf.truncate()

    return {"job_id": job_id, "project_id": project_id, "status": "queued"}


@router.get("/{project_id}/results")
def get_project_results(project_id: str):
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    outputs_dir = project_dir / "outputs"
    files = {}
    if outputs_dir.exists():
        for f in outputs_dir.iterdir():
            if f.is_file() and f.stat().st_size > 0:
                files[f.name] = {
                    "filename": f.name,
                    "size_bytes": f.stat().st_size,
                    "format": f.suffix.lstrip(".").upper(),
                    "download_url": f"/api/projects/{project_id}/files/{f.name}"
                }

    # Load quality report
    report_file = outputs_dir / "quality_report.json"
    report = None
    if report_file.exists():
        try:
            with open(report_file, "r", encoding="utf-8") as rf:
                report = json.load(rf)
        except Exception:
            pass

    # Load contact sheet
    contact_sheet_url = None
    contact_sheet = project_dir / "frames" / "contact_sheet.jpg"
    if contact_sheet.exists():
        contact_sheet_url = f"/api/projects/{project_id}/files/contact_sheet.jpg"

    return {
        "project_id": project_id,
        "files": files,
        "quality_report": report,
        "contact_sheet_url": contact_sheet_url
    }


@router.get("/{project_id}/frames")
def list_project_frames(project_id: str, limit: int = 30):
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    frames_dir = project_dir / "frames"
    if not frames_dir.exists():
        return {"frames": [], "total_count": 0}

    all_frames = sorted([f.name for f in frames_dir.glob("frame_*.jpg")])
    if not all_frames:
        return {"frames": [], "total_count": 0}

    # Sample evenly across the extracted sequence
    if len(all_frames) > limit:
        step = max(1, len(all_frames) // limit)
        sampled = all_frames[::step][:limit]
    else:
        sampled = all_frames

    return {
        "frames": [
            {
                "filename": fname,
                "url": f"/api/projects/{project_id}/files/{fname}"
            }
            for fname in sampled
        ],
        "total_count": len(all_frames)
    }


@router.delete("/{project_id}")
def delete_project(project_id: str):
    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    if job_manager.active_job_for_project(project_id):
        raise HTTPException(status_code=409, detail="A reconstruction job is still running for this project. Cancel it and wait for it to stop first.")

    try:
        shutil.rmtree(project_dir)
        return {"deleted": True, "project_id": project_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {e}")
