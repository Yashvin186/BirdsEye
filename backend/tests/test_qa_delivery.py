import json
from pathlib import Path
import numpy as np
import cv2
from app.services.capture_qa_service import CaptureQAService
from app.services.delivery_service import DeliveryService


def _scene(shift):
    img = np.full((360, 640, 3), 90, np.uint8)
    rng = np.random.default_rng(1)
    for _ in range(80):
        x, y = int(rng.integers(0, 900)), int(rng.integers(0, 360))
        cv2.rectangle(img, (x - shift, y), (x - shift + 30, y + 25), tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
    return img


def test_capture_qa_flags_breaks(tmp_path):
    (tmp_path / "frames").mkdir()
    recs = []
    for i in range(14):
        # second half is an unrelated scene -> tracking break
        img = _scene(i * 6) if i < 7 else cv2.flip(np.random.default_rng(i).integers(0, 255, (360, 640, 3)).astype(np.uint8), 0)
        name = f"frame_{i+1:06d}.jpg"
        cv2.imwrite(str(tmp_path / "frames" / name), img)
        recs.append({"accepted": True, "filename": name, "timestamp_sec": i * 0.5, "sharpness": 200.0})
    (tmp_path / "frames" / "frame_manifest.json").write_text(json.dumps({"records": recs}))
    r = CaptureQAService.analyze(tmp_path, {})
    assert r["available"] and r["tracking_breaks"] >= 1 and r["verdict"] != "good"
    assert (tmp_path / "outputs" / "capture_qa.json").exists()


def test_delivery_package(tmp_path):
    import trimesh
    (tmp_path / "outputs").mkdir()
    g = trimesh.creation.box()
    g.export(str(tmp_path / "outputs" / "model.glb"))
    r = DeliveryService.build(tmp_path, {})
    assert r["available"]
    assert (tmp_path / "outputs" / "birdseye_delivery.zip").exists()
    assert (tmp_path / "outputs" / "delivery" / "README.txt").exists()
