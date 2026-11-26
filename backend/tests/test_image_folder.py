import cv2, numpy as np
from pathlib import Path
from app.services.image_sequence_service import ImageSequenceService as S


def test_find_and_thin(tmp_path):
    sub = tmp_path / "scene" / "images"
    sub.mkdir(parents=True)
    for i in (1, 2, 10, 11, 3):
        cv2.imwrite(str(sub / f"{i:04d}.jpg"), np.full((64, 96, 3), i * 10, np.uint8))
    imgs = S.find_images(tmp_path)
    assert [p.name for p in imgs] == ["0001.jpg", "0002.jpg", "0003.jpg", "0010.jpg", "0011.jpg"]
    proj = tmp_path / "proj"
    info = S.import_folder(proj, str(tmp_path), max_images=10)
    assert info["images_used"] == 5 and (proj / "input" / "image_sequence.json").exists()
    cap = cv2.VideoCapture(str(info["tmp_video"]))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) >= 5


def test_exif_gps_becomes_telemetry(tmp_path):
    from PIL import Image
    d = tmp_path / "photos"; d.mkdir()
    for i in range(8):
        im = Image.new("RGB", (96, 64), (i * 20, 50, 90))
        ex = Image.Exif()
        ex[0x8825] = {1: "N", 2: (12.0, 54.0, 0.0 + i), 3: "E", 4: (74.0, 51.0, 0.0), 6: 25.0 + i}
        im.save(d / f"{i:03d}.jpg", exif=ex)
    info = S.import_folder(tmp_path / "proj", str(d), max_images=10)
    assert info["exif_gps"] and info["images_with_gps"] == 8
    txt = (tmp_path / "proj" / "input" / "telemetry.srt").read_text()
    assert "latitude: 12.9" in txt
    from app.services.geo_service import GeoService
    assert len(GeoService.parse_srt(tmp_path / "proj" / "input" / "telemetry.srt")) == 8
