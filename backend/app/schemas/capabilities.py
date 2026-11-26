from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class DependencyInfo(BaseModel):
    name: str
    available: bool
    version: Optional[str] = None
    path: Optional[str] = None
    details: Optional[str] = None


class PipelineStageCapability(BaseModel):
    stage_id: str
    title: str
    available: bool
    primary_engine: str
    status_note: str


class CapabilitiesResponse(BaseModel):
    os_name: str
    python_version: str
    disk_free_gb: float
    workspace_path: str
    colmap: DependencyInfo
    ffmpeg: DependencyInfo
    opencv: DependencyInfo
    gpu: DependencyInfo
    mesh_tools: DependencyInfo
    power_status: Optional[Dict[str, Any]] = None
    stages: List[PipelineStageCapability]
    ready_for_pipeline: bool
    sfm_engine: str = "colmap"   # 'colmap' | 'pycolmap' (built-in fallback) | 'none'
    setup_recommendations: List[str]


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    workspace_accessible: bool
    colmap_installed: bool
    ffmpeg_installed: bool
    gpu_available: bool
