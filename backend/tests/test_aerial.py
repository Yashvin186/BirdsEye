import numpy as np
from app.services.aerial_service import AerialService


def _write_model(tmp_path, nadir=True, n=12):
    (tmp_path / "cameras.txt").write_text("1 PINHOLE 1000 800 900 900 500 400\n")
    lines = []
    for i in range(n):
        # cameras on a grid 50 above ground; nadir: look straight down (world -z) -> R = diag(1,-1,-1)
        R = np.diag([1.0, -1.0, -1.0]) if nadir else np.eye(3)
        C = np.array([(i % 4) * 8.0, (i // 4) * 8.0, 50.0])
        t = -R @ C
        from scipy.spatial.transform import Rotation
        q = Rotation.from_matrix(R).as_quat()   # x y z w
        lines.append(f"{i+1} {q[3]} {q[0]} {q[1]} {q[2]} {t[0]} {t[1]} {t[2]} 1 f{i}.jpg\n\n")
    (tmp_path / "images.txt").write_text("".join(lines))
    rng = np.random.default_rng(0)
    pts = np.column_stack([rng.uniform(0, 30, 400), rng.uniform(0, 20, 400), rng.normal(0, 0.2, 400)])
    (tmp_path / "points3D.txt").write_text("".join(
        f"{i+1} {p[0]} {p[1]} {p[2]} 100 100 100 0.5 1 0 2 0 3 0\n" for i, p in enumerate(pts)))


def test_detects_nadir_survey(tmp_path):
    _write_model(tmp_path, nadir=True)
    assert AerialService.detect(tmp_path)["is_aerial"] is True


def test_object_orbit_is_not_aerial(tmp_path):
    _write_model(tmp_path, nadir=False)   # cameras look along +z, points sit at z~0 (behind) -> not a survey
    assert AerialService.detect(tmp_path)["is_aerial"] is False
