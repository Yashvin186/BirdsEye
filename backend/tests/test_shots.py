import cv2
import numpy as np
from app.services.frame_service import FrameService


def _write(path, frames, fps=30):
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        vw.write(f)
    vw.release()


def _scene(seed, shift):
    """A textured 'landscape' (many rectangles/circles = real corners) panned left to right."""
    rng = np.random.default_rng(seed)
    big = np.full((360, 1100, 3), 90, np.uint8)
    for _ in range(260):
        c = tuple(int(x) for x in rng.integers(20, 235, 3))
        x, y = int(rng.integers(0, 1050)), int(rng.integers(0, 330))
        if rng.random() < 0.5:
            cv2.rectangle(big, (x, y), (x + int(rng.integers(8, 40)), y + int(rng.integers(8, 40))), c, -1)
        else:
            cv2.circle(big, (x, y), int(rng.integers(4, 20)), c, -1)
    return big[:, shift:shift + 480].copy()


def test_detects_cut_between_two_different_shots(tmp_path):
    a = [_scene(1, i * 2) for i in range(60)]          # slow pan over scene 1
    b = [_scene(2, i * 2) for i in range(60)]          # slow pan over a different scene
    _write(tmp_path / "v.mp4", a + b)
    shots = FrameService.detect_shots(tmp_path / "v.mp4", 30.0)
    assert len(shots) == 2
    assert abs(shots[0]["end_frame"] - 59) <= 10


def test_single_continuous_shot_is_not_split(tmp_path):
    a = [_scene(3, i * 3) for i in range(120)]
    _write(tmp_path / "v.mp4", a)
    assert len(FrameService.detect_shots(tmp_path / "v.mp4", 30.0)) == 1
