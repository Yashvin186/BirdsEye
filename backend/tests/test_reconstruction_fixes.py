"""
Regression tests for the reconstruction fixes. None of these need COLMAP, model weights or a
sample video: they use small synthetic data so they run anywhere.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import cv2
import plyfile

from app.services.frame_service import FrameService
from app.services.colmap_service import ColmapService
from app.services.mesh_service import MeshService
from app.services.ai_depth_service import AiDepthService


def _textured_frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.normal(size=(720, 1280)).astype(np.float32), (0, 0), 6)
    return ((img - img.min()) / (img.max() - img.min()) * 120 + 60).astype(np.uint8)


class TestFrameSimilarity(unittest.TestCase):
    def test_unrelated_frames_are_not_flagged_as_duplicates(self):
        # Old TM_CCORR_NORMED scored unrelated photos ~0.986, i.e. above the 0.985 default threshold.
        a, b = _textured_frame(1), _textured_frame(2)
        self.assertLess(FrameService.compute_spatial_similarity(a, b), 0.5)

    def test_moved_camera_is_not_flagged(self):
        a = _textured_frame(1)
        moved = np.roll(a, 40, axis=1)
        self.assertLess(FrameService.compute_spatial_similarity(a, moved), 0.985)

    def test_identical_frames_are_flagged(self):
        a = _textured_frame(1)
        self.assertGreater(FrameService.compute_spatial_similarity(a, a.copy()), 0.985)

    def test_flat_frames_do_not_crash(self):
        flat = np.full((720, 1280), 128, dtype=np.uint8)
        self.assertEqual(FrameService.compute_spatial_similarity(flat, flat.copy()), 1.0)
        self.assertEqual(FrameService.compute_spatial_similarity(flat, _textured_frame(3)), 0.0)


class TestColmapService(unittest.TestCase):
    def test_matching_cpu_retry_keeps_a_valid_command(self):
        """The GPU->CPU retry used to overwrite the flag NAME (cmd[4]) instead of its value."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if len(calls) == 1:
                return mock.Mock(returncode=1, stdout="", stderr="CUDA error: out of memory")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "colmap").mkdir()
            (project / "colmap" / "database.db").write_bytes(b"x")
            with mock.patch.object(ColmapService, "get_colmap_executable", return_value="colmap"), \
                 mock.patch.object(ColmapService, "use_pycolmap", return_value=False), \
                 mock.patch("app.services.colmap_service.subprocess.run", side_effect=fake_run):
                ColmapService.run_feature_matching(project, strategy="sequential", use_gpu=True)

        self.assertEqual(len(calls), 2)
        retry = calls[1]
        idx = retry.index("--SiftMatching.use_gpu")
        self.assertEqual(retry[idx + 1], "0")
        # Command structure must stay valid: after the executable and sub-command, every bare value
        # must directly follow a --flag (the old bug replaced a flag with "0", leaving two values in a row).
        for i, tok in enumerate(retry):
            if i >= 2 and not tok.startswith("--"):
                self.assertTrue(retry[i - 1].startswith("--"), f"stray value {tok!r} at position {i}: {retry}")

    def test_submodel_stats_report_error_and_track_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp)
            (m / "images.txt").write_text(
                "# header\n"
                "1 1 0 0 0 0 0 0 1 frame_000001.jpg\n0 0 -1\n"
                "2 1 0 0 0 1 0 0 1 frame_000002.jpg\n0 0 -1\n"
            )
            (m / "points3D.txt").write_text(
                "# header\n"
                "1 0 0 5 10 10 10 0.5 1 0 2 0\n"      # error 0.5, track length 2
                "2 1 0 5 10 10 10 1.5 1 1 2 1 1 3\n"   # error 1.5, track length 3
            )
            stats = ColmapService.analyze_submodel("colmap", m)
        self.assertEqual(stats["registered_cams"], 2)
        self.assertEqual(stats["point_count"], 2)
        self.assertAlmostEqual(stats["mean_reproj_error_px"], 1.0)
        self.assertAlmostEqual(stats["mean_track_length"], 2.5)


class TestPoissonMeshing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import open3d  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("open3d not installed")
        # Upper hemisphere only: what a drone flying above an object actually sees.
        rng = np.random.default_rng(0)
        v = rng.normal(size=(60000, 3))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        v = v[v[:, 2] >= 0]
        cls.points = v
        cls.cameras = np.array([[0.0, 0.0, 6.0], [3.0, 0.0, 5.0], [-3.0, 0.0, 5.0], [0.0, 3.0, 5.0]])

    def _mesh(self, fill):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m.ply"
            info = MeshService.poisson_mesh_from_points(
                self.points, out, camera_centers=self.cameras, fill_unseen_regions=fill
            )
            ply = plyfile.PlyData.read(str(out))
            verts = np.column_stack([ply["vertex"]["x"], ply["vertex"]["y"], ply["vertex"]["z"]])
        return info, verts

    def test_unseen_underside_is_left_empty_by_default(self):
        info, verts = self._mesh(fill=False)
        self.assertGreater(info["faces"], 1000)
        self.assertTrue(info["trimmed_unsupported"])
        # Nothing was observed below the equator, so nothing should be invented there.
        self.assertGreater(verts[:, 2].min(), -0.25)

    def test_fill_unseen_regions_closes_the_underside(self):
        info, verts = self._mesh(fill=True)
        self.assertFalse(info["trimmed_unsupported"])
        # Poisson extrapolates a cap below the observed rim (measured ~ -0.13 here with the adaptive depth vs ~ -0.03 when trimmed).
        self.assertLess(verts[:, 2].min(), -0.10)

    def test_too_few_points_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                MeshService.poisson_mesh_from_points(self.points[:100], Path(tmp) / "m.ply")


class TestMeshServiceFallbackIntegration(unittest.TestCase):
    """Full generate_mesh_from_point_cloud() flow with COLMAP's mesher unavailable (the 'Faces: 0' case)."""

    @classmethod
    def setUpClass(cls):
        try:
            import open3d  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("open3d not installed")

    def _project_with_cloud(self, tmp: Path) -> Path:
        import json
        rng = np.random.default_rng(1)
        v = rng.normal(size=(40000, 3))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        v = v[v[:, 2] >= 0].astype(np.float32)
        cols = (np.abs(v) * 255).astype(np.uint8)
        arr = np.empty(len(v), dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"),
                                      ("red", "u1"), ("green", "u1"), ("blue", "u1")])
        for i, c in enumerate("xyz"):
            arr[c] = v[:, i]
        for i, c in enumerate(("red", "green", "blue")):
            arr[c] = cols[:, i]
        out = tmp / "outputs"
        out.mkdir(parents=True)
        plyfile.PlyData([plyfile.PlyElement.describe(arr, "vertex")]).write(str(out / "dense_cloud_filtered.ply"))
        (out / "cameras.json").write_text(json.dumps(
            [{"name": f"frame_{i}.jpg", "position": p} for i, p in enumerate([[0, 0, 6], [3, 0, 5], [-3, 0, 5]])]
        ))
        return tmp

    def test_poisson_fallback_yields_a_complete_export(self):
        with tempfile.TemporaryDirectory() as t:
            project = self._project_with_cloud(Path(t))
            with mock.patch.object(ColmapService, "get_colmap_executable", return_value="/bin/false"):
                res = MeshService.generate_mesh_from_point_cloud(
                    project_dir=project,
                    preferred_cloud_path=project / "outputs" / "dense_cloud_filtered.ply",
                )
            self.assertEqual(res["status"], "completed", res.get("reason"))
            self.assertEqual(res["mesh_method"], "poisson_trimmed")
            self.assertEqual(res["unseen_regions"], "left_empty")
            self.assertGreater(res["face_count"], 1000)
            for key in ("obj_path", "glb_path", "mesh_ply_path"):
                self.assertTrue(res[key] and Path(res[key]).stat().st_size > 0, f"{key} missing/empty")

    def test_fill_flag_is_reported_as_extrapolated(self):
        with tempfile.TemporaryDirectory() as t:
            project = self._project_with_cloud(Path(t))
            with mock.patch.object(ColmapService, "get_colmap_executable", return_value="/bin/false"):
                res = MeshService.generate_mesh_from_point_cloud(
                    project_dir=project,
                    preferred_cloud_path=project / "outputs" / "dense_cloud_filtered.ply",
                    fill_unseen_regions=True,
                )
            self.assertEqual(res["status"], "completed", res.get("reason"))
            self.assertEqual(res["mesh_method"], "poisson_extrapolated")
            self.assertEqual(res["unseen_regions"], "extrapolated")


class TestAiDepthMerge(unittest.TestCase):
    def test_vertex_extraction_ignores_normals(self):
        dtype = [("x", "f4"), ("y", "f4"), ("z", "f4"), ("nx", "f4"), ("ny", "f4"), ("nz", "f4"),
                 ("red", "u1"), ("green", "u1"), ("blue", "u1")]
        arr = np.zeros(4, dtype=dtype)
        arr["x"] = [0, 1, 2, 3]
        arr["red"] = 200
        el = plyfile.PlyElement.describe(arr, "vertex")
        pts, cols = AiDepthService._vertex_xyz_rgb(el)
        self.assertEqual(pts.shape, (4, 3))
        self.assertEqual(cols.shape, (4, 3))
        self.assertTrue((cols[:, 0] == 200).all())

    def test_ai_points_only_fill_gaps(self):
        rng = np.random.default_rng(0)
        # Measured cloud: dense square patch, x in [0,1].
        base = np.column_stack([rng.uniform(0, 1, 20000), rng.uniform(0, 1, 20000), np.zeros(20000)])
        on_surface = np.column_stack([rng.uniform(0.1, 0.9, 50), rng.uniform(0.1, 0.9, 50), np.zeros(50)])
        in_gap = np.column_stack([rng.uniform(3, 4, 50), rng.uniform(3, 4, 50), np.zeros(50)])
        keep = AiDepthService.select_void_filling_points(base, np.vstack([on_surface, in_gap]))
        self.assertFalse(keep[:50].any(), "AI points on top of measured surface must be dropped (ghost layer)")
        self.assertTrue(keep[50:].all(), "AI points in a real gap must be kept")

    def test_disparity_mask_is_scale_invariant(self):
        # Same scene, depth model output scaled x100: the sky mask must behave identically.
        h, w = 64, 64
        disp = np.linspace(0, 1, w, dtype=np.float32)[None, :].repeat(h, axis=0)
        img = np.full((h, w, 3), 90, dtype=np.uint8)
        args = dict(image_bgr=img, scale=1.0, shift=0.0, focal_len=100.0, cx=32.0, cy=32.0,
                    R_cam=np.eye(3), t_cam=np.zeros(3), stride=1)
        n1 = len(AiDepthService.backproject_dense_points(disparity_map=disp + 0.5, **args)[0])
        n2 = len(AiDepthService.backproject_dense_points(disparity_map=(disp + 0.5) * 100, **args)[0])
        self.assertGreater(n1, 0)
        # Backprojection depth differs with scale, but the masked-in pixel set must not.
        self.assertEqual(n1, n2)


if __name__ == "__main__":
    unittest.main()
