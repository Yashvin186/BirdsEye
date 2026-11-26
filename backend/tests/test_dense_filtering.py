import unittest
import tempfile
import shutil
from pathlib import Path
import numpy as np
import plyfile

from app.services.dense_service import DenseService


def create_test_ply(file_path: Path, points: np.ndarray, colors: np.ndarray = None):
    num_pts = points.shape[0]
    vertex_dtype = [
        ('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
        ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')
    ]
    arr = np.empty(num_pts, dtype=vertex_dtype)
    for i, col in enumerate(('x', 'y', 'z')):
        arr[col] = points[:, i]

    if colors is None:
        colors = np.random.randint(0, 255, (num_pts, 3), dtype='u1')

    for i, col in enumerate(('red', 'green', 'blue')):
        arr[col] = colors[:, i]

    el = plyfile.PlyElement.describe(arr, 'vertex')
    file_path.parent.mkdir(parents=True, exist_ok=True)
    plyfile.PlyData([el], text=False).write(str(file_path))


class TestDenseFiltering(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="birdseye_filter_test_"))
        self.raw_ply = self.test_dir / "raw_dense.ply"
        self.filt_ply = self.test_dir / "filtered_dense.ply"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sor_filtering_removes_distant_outliers(self):
        # 1000 tight core points in [0, 10]
        np.random.seed(42)
        core_pts = np.random.uniform(0, 10, (1000, 3))
        # 5 extreme outliers placed far outside
        outlier_pts = np.array([
            [500.0, 500.0, 500.0],
            [-500.0, -500.0, -500.0],
            [1000.0, 0.0, 0.0],
            [0.0, 1000.0, 0.0],
            [0.0, 0.0, 1000.0]
        ])
        all_pts = np.vstack([core_pts, outlier_pts])
        create_test_ply(self.raw_ply, all_pts)

        res = DenseService.filter_statistical_outliers(
            input_path=self.raw_ply,
            output_path=self.filt_ply,
            k=20,
            std_multiplier=2.0
        )

        self.assertEqual(res["status"], "passed")
        self.assertEqual(res["raw_points"], 1005)
        self.assertGreaterEqual(res["filtered_points"], 1000)
        self.assertGreater(res["outliers_removed"], 0)
        self.assertTrue(res["quality_gate"]["passed"])
        self.assertTrue(self.filt_ply.exists())
        self.assertGreater(self.filt_ply.stat().st_size, 0)

        # Raw file must remain completely untouched
        self.assertTrue(self.raw_ply.exists())
        raw_data = plyfile.PlyData.read(str(self.raw_ply))
        self.assertEqual(len(raw_data["vertex"]), 1005)

        # Bounding box span tightened significantly
        self.assertLess(res["filtered_bounding_box"]["span"][0], 50.0)
        self.assertLess(res["filtered_bounding_box"]["span"][1], 50.0)
        self.assertLess(res["filtered_bounding_box"]["span"][2], 50.0)

    def test_quality_gate_checks_minimum_points(self):
        # Small cloud with only 5 points below threshold
        pts = np.random.uniform(0, 1, (5, 3))
        create_test_ply(self.raw_ply, pts)

        res = DenseService.filter_statistical_outliers(
            input_path=self.raw_ply,
            output_path=self.filt_ply,
            k=2,
            std_multiplier=2.0
        )

        self.assertEqual(res["status"], "flagged")
        self.assertFalse(res["quality_gate"]["passed"])
        self.assertFalse(res["quality_gate"]["checks"]["minimum_points"])

    def test_handles_non_finite_coordinates_safely(self):
        # 200 normal points + 2 NaN/Inf points
        pts = np.random.uniform(0, 10, (200, 3))
        pts[0, 0] = np.nan
        pts[1, 1] = np.inf
        create_test_ply(self.raw_ply, pts)

        res = DenseService.filter_statistical_outliers(
            input_path=self.raw_ply,
            output_path=self.filt_ply,
            k=10,
            std_multiplier=2.0
        )

        self.assertFalse(res["quality_gate"]["checks"]["all_finite"])
        self.assertTrue(self.filt_ply.exists())


if __name__ == "__main__":
    unittest.main()

