from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class VideoMetadata(BaseModel):
    filename: str
    original_filename: str
    size_bytes: int
    duration_seconds: float
    fps: float
    frame_count: int
    width: int
    height: int
    codec: str
    aspect_ratio: str
    has_audio: bool = False
    has_gps: bool = False
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_altitude: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)


class OptionalFlightParameters(BaseModel):
    camera_model: Optional[str] = None
    focal_length_mm: Optional[float] = None
    sensor_width_mm: Optional[float] = None
    flight_height_m: Optional[float] = None
    known_scale_distance_m: Optional[float] = None
    gcp_points: Optional[List[Dict[str, Any]]] = None


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    flight_params: Optional[OptionalFlightParameters] = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: str
    updated_at: str
    status: str
    video_uploaded: bool
    video_metadata: Optional[VideoMetadata] = None
    has_results: bool = False
    output_files_count: int = 0
