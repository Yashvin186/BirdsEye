from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class PipelineStageId(str, Enum):
    VALIDATING = "validating"
    EXTRACTING_FRAMES = "extracting_frames"
    PREPROCESSING = "preprocessing"
    FEATURE_MATCHING = "feature_matching"
    SFM = "sfm"
    DENSE_RECONSTRUCTION = "dense_reconstruction"
    AI_DEPTH = "ai_depth"
    MESHING_TEXTURING = "meshing_texturing"
    GEOREFERENCING_EVALUATION = "georeferencing_evaluation"
    PACKAGING = "packaging"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"


class StageDetail(BaseModel):
    stage_id: str
    title: str
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    progress_percent: Optional[int] = None
    log_preview: List[str] = Field(default_factory=list)
    output_files: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class PipelineConfigRequest(BaseModel):
    sampling_fps: float = Field(2.0, ge=0.2, le=10.0, description="Target extracted frames per second")
    max_frames: int = Field(200, ge=10, le=1000, description="Maximum candidate frames to extract")
    blur_threshold: float = Field(80.0, ge=10.0, le=500.0, description="Laplacian variance threshold for blur filtering")
    similarity_threshold: float = Field(0.985, ge=0.5, le=0.999, description="Spatial correlation threshold to filter stationary frames (0.985 recommended)")
    auto_shot_select: bool = Field(True, description="If the video is an edited clip with several shots, use only the longest continuous shot")
    scene_mode: str = Field("auto", pattern="^(auto|aerial|object)$", description="auto-detect, force aerial survey (nadir flight over an area) or object (orbit) mode")
    matching_strategy: str = Field("sequential", description="'sequential' or 'exhaustive'")
    gpu_mode: str = Field("auto", description="'auto' (auto-switch based on AC charger), 'cuda' (NVIDIA GPU), or 'cpu' (battery safe)")
    enable_dense_mvs: bool = Field(True, description="Run patch-match dense reconstruction if supported")
    enable_ai_depth: bool = Field(False, description="Run AI monocular depth estimation and densification (Depth Anything V2)")
    enable_meshing: bool = Field(True, description="Generate 3D surface mesh from point cloud")
    enable_texturing: bool = Field(False, description="Deprecated and ignored: surfaces are vertex-coloured from the photos; UV texture baking is not implemented.")
    quality_preset: str = Field(
        "balanced", pattern="^(fast|balanced|high)$",
        description="'fast' (quick preview), 'balanced' (default) or 'high' (slowest, sharpest when zoomed). Sets frame size, dense-stereo resolution and mesh detail together."
    )
    isolate_subject: bool = Field(
        True,
        description=(
            "Crop the dense cloud to the region SfM verified, removing distant background "
            "(mountains, sky, river) whose short-baseline depth is unreliable and forms giant sheets."
        )
    )
    cpu_stereo_fallback: bool = Field(
        True,
        description="If CUDA/MVS is unavailable, build the dense cloud on the CPU with stereo matching (noisier, but works anywhere)."
    )
    fill_unseen_regions: bool = Field(
        False,
        description=(
            "Close the surface over regions the video never observed (undersides, hidden sides). "
            "OFF (default): unobserved regions are left empty - honest. "
            "ON: they are filled by Poisson extrapolation - looks complete, but those parts are NOT measured."
        )
    )


class JobStatusResponse(BaseModel):
    job_id: str
    project_id: str
    status: str  # queued, running, completed, failed, cancelled
    current_stage: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    stages: List[StageDetail] = Field(default_factory=list)
    output_files: Dict[str, Any] = Field(default_factory=dict)
    summary_report: Optional[Dict[str, Any]] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
