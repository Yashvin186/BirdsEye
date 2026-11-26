from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.video_service import VideoService

router = APIRouter(prefix="/api/projects", tags=["Files"])


@router.get("/{project_id}/files/{filename}")
def download_project_file(project_id: str, filename: str):
    # Path traversal validation
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid file name: path traversal characters detected.")

    project_dir = VideoService.get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    # Search in outputs or frames or input
    candidates = [
        project_dir / "outputs" / filename,
        project_dir / "frames" / filename,
        project_dir / "input" / filename,
    ]

    target = None
    for cand in candidates:
        if cand.exists() and cand.is_file():
            # Ensure resolved target is within project_dir
            if str(cand.resolve()).startswith(str(project_dir.resolve())):
                target = cand
                break

    if not target:
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in project workspace.")

    ext = target.suffix.lower()
    media_types = {
        ".ply": "application/octet-stream",
        ".obj": "text/plain",
        ".mtl": "text/plain",
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".json": "application/json",
        ".csv": "text/csv",
        ".md": "text/markdown",
        ".mp4": "video/mp4"
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(target),
        filename=filename,
        media_type=media_type
    )
