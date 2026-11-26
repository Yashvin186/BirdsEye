import os
import shutil
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (two levels up from backend/app)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _get_default_colmap() -> str:
    cuda_bat = PROJECT_ROOT / "bin" / "colmap" / "COLMAP-3.9.1-windows-cuda" / "COLMAP.bat"
    if cuda_bat.exists():
        return str(cuda_bat)
    no_cuda_bat = PROJECT_ROOT / "bin" / "colmap" / "COLMAP-3.9.1-windows-no-cuda" / "COLMAP.bat"
    if no_cuda_bat.exists():
        return str(no_cuda_bat)
    found = shutil.which("colmap")
    return found if found else "colmap"


def _get_default_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    d_apps = Path("D:/Apps/ffmpeg/bin/ffmpeg.exe")
    if d_apps.exists():
        return str(d_apps)
    return "ffmpeg"


class Settings(BaseSettings):
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Workspace directory
    BIRDS_EYE_WORKSPACE: Path = PROJECT_ROOT / "workspace"

    # External executable paths
    COLMAP_EXE: str = _get_default_colmap()
    FFMPEG_EXE: str = _get_default_ffmpeg()

    # Constraints
    MAX_UPLOAD_SIZE_MB: int = 1024
    MAX_VIDEO_DURATION_SEC: int = 1200  # 20 minutes

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure workspace exists
settings.BIRDS_EYE_WORKSPACE.mkdir(parents=True, exist_ok=True)
