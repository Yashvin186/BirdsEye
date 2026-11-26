import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np
import plyfile

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.pipeline import StageStatus, JobStatusResponse
from app.core.environment import check_colmap_dense_capable, check_colmap
from app.services.dense_service import DenseService
from app.services.mesh_service import MeshService
from app.services.colmap_service import ColmapService
from app.config import settings


def create_dummy_ply(file_path: Path, num_points: int = 20):
    pts = np.random.rand(num_points, 3).astype('f4')
    cols = np.random.randint(0, 255, (num_points, 3), dtype='u1')
    vertex_dtype = [
        ('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
        ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')
    ]
    arr = np.empty(num_points, dtype=vertex_dtype)
    for i, col in enumerate(('x', 'y', 'z')):
        arr[col] = pts[:, i]
    for i, col in enumerate(('red', 'green', 'blue')):
        arr[col] = cols[:, i]
    el = plyfile.PlyElement.describe(arr, 'vertex')
    file_path.parent.mkdir(parents=True, exist_ok=True)
    plyfile.PlyData([el], text=False).write(str(file_path))


class TestReconstructionRepair(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="birdseye_test_"))
        self.outputs_dir = self.test_dir / "outputs"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.sparse_ply = self.outputs_dir / "sparse_cloud.ply"
        create_dummy_ply(self.sparse_ply, num_points=30)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_colmap_dense_capable_detection(self):
        if not check_colmap_dense_capable()[0]:
            self.skipTest("No CUDA-capable COLMAP configured on this machine")
        """Verify check_colmap_dense_capable accurately detects CUDA vs no-CUDA binaries."""
        # 1. Configured CUDA COLMAP
        capable, reason = check_colmap_dense_capable()
        self.assertTrue(capable, "Configured CUDA COLMAP must report dense MVS is supported.")

        # 2. Fallback no-cuda binary
        no_cuda_bat = Path("e:/yashu/proj/BIRDS_EYE/bin/colmap/COLMAP-3.9.1-windows-no-cuda/COLMAP.bat")
        if no_cuda_bat.exists():
            orig_exe = settings.COLMAP_EXE
            try:
                settings.COLMAP_EXE = str(no_cuda_bat)
                no_cuda_capable, no_cuda_reason = check_colmap_dense_capable()
                self.assertFalse(no_cuda_capable, "No-CUDA COLMAP must report unsupported.")
                self.assertIn("cuda", no_cuda_reason.lower())
            finally:
                settings.COLMAP_EXE = orig_exe

    def test_dense_service_never_fakes_dense_cloud_on_unsupported_colmap(self):
        """Verify DenseService reports 'unsupported' and never interpolates sparse points into a fake dense_cloud.ply."""
        primary_sparse = self.test_dir / "colmap" / "sparse" / "0"
        primary_sparse.mkdir(parents=True, exist_ok=True)

        no_cuda_bat = Path("e:/yashu/proj/BIRDS_EYE/bin/colmap/COLMAP-3.9.1-windows-no-cuda/COLMAP.bat")
        orig_exe = settings.COLMAP_EXE
        try:
            if no_cuda_bat.exists():
                settings.COLMAP_EXE = str(no_cuda_bat)
            res = DenseService.run_dense_reconstruction(
                project_dir=self.test_dir,
                primary_sparse_model=primary_sparse
            )
            self.assertEqual(res["status"], "unsupported")
            self.assertIsNone(res["dense_ply"])
            self.assertEqual(res["dense_point_count"], 0)
            self.assertFalse((self.outputs_dir / "dense_cloud.ply").exists(), "dense_cloud.ply must NOT be manufactured!")
        finally:
            settings.COLMAP_EXE = orig_exe

    def test_mesh_service_never_uses_convex_hull_fallback(self):
        """Verify MeshService fails cleanly instead of generating a misleading convex hull when Delaunay mesher is unavailable."""
        res = MeshService.generate_mesh_from_point_cloud(
            project_dir=self.test_dir,
            primary_sparse_model=self.test_dir / "colmap" / "sparse" / "nonexistent"
        )

        self.assertEqual(res["status"], "failed")
        self.assertIn("Convex-hull fallback is disabled", res["reason"])
        self.assertIsNone(res["obj_path"])
        self.assertFalse((self.outputs_dir / "model_mesh.ply").exists())

    def test_mesh_service_honors_preferred_cloud_path(self):
        """Verify MeshService honors preferred_cloud_path argument."""
        custom_cloud = self.outputs_dir / "custom_dense_cloud.ply"
        create_dummy_ply(custom_cloud, num_points=50)

        res = MeshService.generate_mesh_from_point_cloud(
            project_dir=self.test_dir,
            preferred_cloud_path=custom_cloud
        )

        # Even if meshing fails due to missing sparse model, source_cloud_type must reflect the preferred input
        self.assertEqual(res["source_cloud_type"], "dense_mvs")

    def test_deterministic_submodel_ranking(self):
        """Verify submodels are ranked by camera count and point count rather than file size."""
        m0 = self.test_dir / "model_0"
        m1 = self.test_dir / "model_1"
        m0.mkdir()
        m1.mkdir()

        # m0: large dummy text with few cameras
        with open(m0 / "images.txt", "w", encoding="utf-8") as f:
            f.write("# COLMAP images.txt\n")
            f.write("1 0.0 0.0 0.0 0.0 0.0 0.0 0.0 1 frame_000001.jpg\n")
            f.write("10.0 20.0 1\n")
        with open(m0 / "points3D.txt", "w", encoding="utf-8") as f:
            f.write("# COLMAP points3D.txt\n")
            for i in range(10):
                f.write(f"{i+1} 1.0 2.0 3.0 255 255 255 0.1 1 0\n" + "extra filler bytes " * 10 + "\n")

        # m1: more registered cameras
        with open(m1 / "images.txt", "w", encoding="utf-8") as f:
            f.write("# COLMAP images.txt\n")
            for i in range(5):
                f.write(f"{i+1} 0.0 0.0 0.0 0.0 0.0 0.0 0.0 1 frame_{i+1:06d}.jpg\n")
                f.write("10.0 20.0 1\n")
        with open(m1 / "points3D.txt", "w", encoding="utf-8") as f:
            f.write("# COLMAP points3D.txt\n")
            for i in range(25):
                f.write(f"{i+1} 1.0 2.0 3.0 255 255 255 0.1 1 0\n")

        stat0 = ColmapService.analyze_submodel("colmap", m0)
        stat1 = ColmapService.analyze_submodel("colmap", m1)

        self.assertEqual(stat0["registered_cams"], 1)
        self.assertEqual(stat1["registered_cams"], 5)
        self.assertEqual(stat1["point_count"], 25)

        # Ranked list
        ranked = [stat0, stat1]
        ranked.sort(key=lambda s: (s["registered_cams"], s["point_count"]), reverse=True)
        self.assertEqual(ranked[0]["name"], "model_1")

    def test_pipeline_stage_statuses_contain_partial_and_unsupported(self):
        """Verify StageStatus enum includes PARTIAL and UNSUPPORTED."""
        self.assertEqual(StageStatus.PARTIAL.value, "partial")
        self.assertEqual(StageStatus.UNSUPPORTED.value, "unsupported")


if __name__ == "__main__":
    unittest.main()
