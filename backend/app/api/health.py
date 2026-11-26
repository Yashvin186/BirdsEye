from fastapi import APIRouter
from app.schemas.capabilities import HealthResponse
from app.config import settings
from app.core.environment import check_colmap, check_ffmpeg, check_gpu

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    colmap_info = check_colmap()
    ffmpeg_info = check_ffmpeg()
    gpu_info = check_gpu()

    return HealthResponse(
        status="ok",
        app_name="Birds Eye 3D Reconstruction",
        version="1.0.0",
        workspace_accessible=settings.BIRDS_EYE_WORKSPACE.exists(),
        colmap_installed=colmap_info.available,
        ffmpeg_installed=ffmpeg_info.available,
        gpu_available=gpu_info.available
    )
