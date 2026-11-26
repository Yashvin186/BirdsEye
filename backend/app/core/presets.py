"""
Quality presets: one switch that trades runtime against detail across the whole pipeline.

Runtime is dominated by (1) how many pixels feature extraction and dense stereo process and
(2) how many frames are used. Detail when zooming is limited by the dense-stereo image size and the
mesh face budget. The presets set all of these together so the stages stay consistent.
"""
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class QualityPreset:
    name: str
    max_frames: int          # upper bound on frames used (the user's own max_frames can only lower it)
    frame_dim: int           # long edge, px, frames are saved at (0 = keep the video's size)
    sift_dim: int            # feature-extraction image size
    sift_features: int       # SIFT features per image
    mvs_dim: int             # dense stereo / undistortion image size
    mesh_faces: int          # face budget of the final mesh
    poisson_max_depth: int   # highest Poisson octree depth allowed
    ai_stride: int           # pixel stride when back-projecting AI depth (smaller = denser)
    ai_frames: int           # key frames used by the AI-depth step


PRESETS: Dict[str, QualityPreset] = {
    "fast": QualityPreset("fast", 80, 1280, 1280, 4096, 1000, 150_000, 9, 8, 8),
    "balanced": QualityPreset("balanced", 140, 1920, 1920, 8192, 1600, 350_000, 10, 4, 10),
    "high": QualityPreset("high", 220, 2560, 2560, 8192, 2400, 700_000, 11, 3, 14),
}
DEFAULT_PRESET = "balanced"


def get_preset(name: str) -> QualityPreset:
    return PRESETS.get((name or DEFAULT_PRESET).lower(), PRESETS[DEFAULT_PRESET])
