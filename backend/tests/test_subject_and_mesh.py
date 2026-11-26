"""Tests for subject isolation, CPU stereo helpers and mesh cleanup. Synthetic data only."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import plyfile

from app.services.subject_service import SubjectService
from app.services.cpu_dense_service import CpuDenseService
from app.services.mesh_service import MeshService


def _write_points3d(path: Path, pts):
    lines = ["# 3D point list"]
    for i, p in enumerate(pts):
        lines.append(f"{i+1} {p[0]} {p[1]} {p[2]} 10 10 10 0.5 1 0 2 1 3 2")
    (path / "points3D.txt").write_text("\n".join(lines))


def _write_ply(path: Path, xyz):
    v = np.zeros(len(xyz), dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"),
                                  ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    v["x"], v["y"], v["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    plyfile.PlyData([plyfile.PlyElement.describe(v, "vertex")]).write(str(path))


class TestSubjectIsolation(unittest.TestCase):
    def test_far_background_is_removed_subject_kept(self):
        rng = np.random.default_rng(0)
        subject = rng.uniform(-10, 10, (2000, 3))
        background = rng.uniform(-10, 10, (3000, 3)) + np.array([0, 0, 600.0])
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            _write_points3d(d, subject[:300])
            _write_ply(d / "in.ply", np.vstack([subject, background]))
            res = SubjectService.isolate_ply(d / "in.ply", d / "out.ply", d)
            self.assertTrue(res["applied"])
            self.assertGreater(res["kept_points"], 1900)
            self.assertLess(res["kept_points"], 2200)

    def test_skips_when_too_few_trusted_points(self):
        rng = np.random.default_rng(1)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            _write_points3d(d, rng.uniform(-1, 1, (10, 3)))
            _write_ply(d / "in.ply", rng.uniform(-1, 1, (500, 3)))
            res = SubjectService.isolate_ply(d / "in.ply", d / "out.ply", d)
            self.assertFalse(res["applied"])
            self.assertEqual(res["kept_points"], 500)

    def test_high_error_and_short_tracks_are_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "points3D.txt").write_text(
                "1 0 0 0 1 1 1 3.0 1 0 2 1 3 2\n"      # error too high
                "2 1 1 1 1 1 1 0.4 1 0\n"              # track too short
                "3 2 2 2 1 1 1 0.4 1 0 2 1 3 2\n")     # good
            pts = SubjectService.read_sparse_points(d)
            self.assertEqual(len(pts), 1)


class TestCpuDenseHelpers(unittest.TestCase):
    def test_quaternion_identity_and_rotation(self):
        np.testing.assert_allclose(CpuDenseService._quat_to_rot(1, 0, 0, 0), np.eye(3), atol=1e-9)
        r = CpuDenseService._quat_to_rot(np.sqrt(0.5), 0, 0, np.sqrt(0.5))  # 90 deg about z
        np.testing.assert_allclose(r @ np.array([1, 0, 0]), [0, 1, 0], atol=1e-9)


class TestMeshCleanup(unittest.TestCase):
    def test_poisson_caps_faces_and_removes_floating_islands(self):
        rng = np.random.default_rng(2)
        n = 40000
        v = rng.normal(size=(n, 3)); v /= np.linalg.norm(v, axis=1, keepdims=True)
        sphere = v * 10
        island = rng.normal(size=(300, 3)) * 0.05 + np.array([60, 0, 0])
        pts = np.vstack([sphere, island])
        with tempfile.TemporaryDirectory() as d:
            old = MeshService.MAX_FACES
            MeshService.MAX_FACES = 5000
            try:
                out = Path(d) / "m.ply"
                res = MeshService.poisson_mesh_from_points(pts, out, camera_centers=np.array([[0, 0, 0.0]]))
            finally:
                MeshService.MAX_FACES = old
            self.assertLessEqual(res["faces"], 5200)
            import open3d as o3d
            m = o3d.io.read_triangle_mesh(str(out))
            self.assertLess(np.asarray(m.vertices)[:, 0].max(), 30)  # island at x=60 is gone


class TestMeshGeometryCleanup(unittest.TestCase):
    def test_far_sheet_and_bridge_triangles_are_removed_with_sparse_volume(self):
        import trimesh
        sphere = trimesh.creation.icosphere(subdivisions=4, radius=10.0)
        far = trimesh.Trimesh(vertices=[[200, 0, 0], [260, 0, 0], [200, 60, 0]], faces=[[0, 1, 2]])
        mesh = trimesh.util.concatenate([sphere, far])
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            _write_points3d(d, sphere.vertices[:300])
            out = MeshService.clean_mesh_geometry(mesh, d)
        self.assertEqual(len(out.faces), len(sphere.faces))
        self.assertLess(out.bounds[1][0], 20)


class TestQualityPresets(unittest.TestCase):
    def test_presets_are_ordered_and_unknown_falls_back(self):
        from app.core.presets import get_preset
        f, b, h = get_preset("fast"), get_preset("balanced"), get_preset("high")
        self.assertLess(f.mvs_dim, b.mvs_dim)
        self.assertLess(b.mvs_dim, h.mvs_dim)
        self.assertLess(f.mesh_faces, b.mesh_faces)
        self.assertEqual(get_preset("nonsense").name, "balanced")

    def test_frames_are_downscaled_and_only_sampled_frames_kept(self):
        import cv2, shutil
        from app.services.frame_service import FrameService
        from app.schemas.pipeline import PipelineConfigRequest
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); (d / "input").mkdir()
            vid = d / "input" / "source_video.mp4"
            w = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"mp4v"), 10, (2560, 1440))
            rng = np.random.default_rng(0)
            base = cv2.GaussianBlur(rng.integers(0, 255, (1440, 2560, 3), dtype=np.uint8), (0, 0), 3)
            for i in range(30):
                w.write(np.roll(base, i * 40, axis=1))
            w.release()
            res = FrameService.extract_and_preprocess(
                project_dir=d, config=PipelineConfigRequest(quality_preset="fast", blur_threshold=10.0))
            self.assertGreater(res["accepted_count"], 0)
            img = cv2.imread(str(next((d / "frames").glob("frame_*.jpg"))))
            self.assertLessEqual(max(img.shape[:2]), 1280)


class TestCoverage(unittest.TestCase):
    def _model(self, d: Path, angles_deg, radius=10.0):
        (d / "cameras.txt").write_text("1 SIMPLE_PINHOLE 100 100 100 50 50\n")
        lines, rng = [], np.random.default_rng(0)
        for i, a in enumerate(angles_deg):
            a = np.radians(a)
            C = np.array([radius * np.cos(a), 0.0, radius * np.sin(a)])
            # camera looks at the origin; world y is "down" for the camera (COLMAP convention), so R maps world->camera
            z = -C / np.linalg.norm(C); y = np.array([0.0, 1.0, 0.0]); x = np.cross(y, z); x /= np.linalg.norm(x); y = np.cross(z, x)
            R = np.stack([x, y, z]); t = -R @ C
            from scipy.spatial.transform import Rotation
            q = Rotation.from_matrix(R).as_quat()          # x,y,z,w
            lines.append(f"{i+1} {q[3]} {q[0]} {q[1]} {q[2]} {t[0]} {t[1]} {t[2]} 1 f{i}.jpg\n\n")
        (d / "images.txt").write_text("".join(lines))
        _write_points3d(d, rng.normal(size=(100, 3)))

    def test_single_pass_is_limited_and_full_orbit_is_good(self):
        from app.services.coverage_service import CoverageService
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self._model(Path(a), np.linspace(0, 15, 12))
            self._model(Path(b), np.linspace(0, 340, 24))
            ra, rb = CoverageService.analyze(Path(a)), CoverageService.analyze(Path(b))
        self.assertEqual(ra["verdict"], "single_side")
        self.assertLess(ra["angular_span_deg"], 30)
        self.assertEqual(rb["verdict"], "full_orbit")
        self.assertGreater(rb["coverage_percent"], 90)


if __name__ == "__main__":
    unittest.main()
