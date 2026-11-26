import unittest
import numpy as np
from pathlib import Path

from app.services.ai_depth_service import AiDepthService


@unittest.skipUnless(AiDepthService.is_available()[0], "Depth Anything V2 weights not installed (run tools/download_depth_model.py)")
class TestAiDepthService(unittest.TestCase):
    def test_01_service_availability(self):
        available, reason = AiDepthService.is_available()
        self.assertTrue(available, f"AiDepthService must be available: {reason}")
        self.assertTrue(AiDepthService.get_model_path().exists())

    def test_02_predict_disparity_on_image(self):
        # Create a synthetic 3-channel test image (e.g. 640x480)
        np.random.seed(42)
        dummy_img = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)

        disp = AiDepthService.predict_disparity(dummy_img, target_size=280)
        self.assertEqual(disp.shape, (480, 640))
        self.assertTrue(np.all(np.isfinite(disp)))
        self.assertGreater(float(disp.max()), 0.0)

    def test_03_align_scale_and_shift_ransac(self):
        # Generate synthetic disparity and ground truth inverse depth
        true_scale = 1.5
        true_shift = 0.2

        disparities = np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
        inv_depths = true_scale * disparities + true_shift
        depths = 1.0 / inv_depths

        disp_map = np.ones((100, 100), dtype=np.float32)
        pts2d = []
        for i, d in enumerate(disparities):
            disp_map[i * 10, i * 10] = d
            pts2d.append([float(i * 10), float(i * 10)])

        s, o, inliers = AiDepthService.align_scale_and_shift(
            disparity_map=disp_map,
            points2d=np.array(pts2d),
            camera_depths=depths
        )

        self.assertAlmostEqual(s, true_scale, places=1)
        self.assertAlmostEqual(o, true_shift, places=1)
        self.assertGreaterEqual(inliers, 4)

    def test_04_backproject_dense_points(self):
        h, w = 100, 100
        disp_map = np.full((h, w), 2.0, dtype=np.float32)
        img_bgr = np.full((h, w, 3), 128, dtype=np.uint8)

        R = np.eye(3)
        t = np.zeros(3)

        pts, colors = AiDepthService.backproject_dense_points(
            image_bgr=img_bgr,
            disparity_map=disp_map,
            scale=1.0,
            shift=0.0,
            focal_len=100.0,
            cx=50.0,
            cy=50.0,
            R_cam=R,
            t_cam=t,
            stride=10
        )

        self.assertGreater(len(pts), 0)
        self.assertEqual(pts.shape[1], 3)
        self.assertEqual(colors.shape[1], 3)
        # Depth should be 1 / (1.0 * 2.0) = 0.5
        self.assertTrue(np.allclose(pts[:, 2], 0.5, atol=0.01))

    def test_05_run_ai_densification_pipeline(self):
        import tempfile
        import cv2

        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = Path(tmpdir)
            frames_dir = proj_dir / "frames"
            frames_dir.mkdir(parents=True)
            sparse_dir = proj_dir / "colmap" / "sparse" / "0"
            sparse_dir.mkdir(parents=True)

            # Create dummy keyframe
            test_img = np.full((120, 160, 3), 180, dtype=np.uint8)
            cv2.imwrite(str(frames_dir / "frame_001.jpg"), test_img)

            # Create cameras.txt
            with open(sparse_dir / "cameras.txt", "w") as f:
                f.write("1 SIMPLE_RADIAL 160 120 150.0 80.0 60.0 0.0\n")

            # Create points3D.txt (3 points)
            with open(sparse_dir / "points3D.txt", "w") as f:
                f.write("1 0.0 0.0 2.0 255 255 255 0.1 1 0\n")
                f.write("2 0.5 0.5 2.5 255 255 255 0.1 1 1\n")
                f.write("3 -0.5 -0.5 1.8 255 255 255 0.1 1 2\n")

            # Create images.txt
            with open(sparse_dir / "images.txt", "w") as f:
                f.write("1 1.0 0.0 0.0 0.0 0.0 0.0 0.0 1 frame_001.jpg\n")
                f.write("80.0 60.0 1 100.0 70.0 2 60.0 50.0 3\n")

            # Run densification
            res = AiDepthService.run_ai_densification(
                project_dir=proj_dir,
                primary_sparse_dir=sparse_dir,
                max_frames=1,
                stride=16
            )

            self.assertEqual(res["status"], "completed")
            self.assertGreater(res["ai_points"], 0)
            self.assertTrue(Path(res["ai_ply_path"]).exists())


if __name__ == "__main__":
    unittest.main()

