import unittest
import os
import shutil
import json
import time
from pathlib import Path

from app.config import settings
from app.schemas.project import ProjectCreateRequest
from app.schemas.pipeline import PipelineConfigRequest
from app.api.projects import (
    create_project,
    list_projects,
    get_project,
    load_sample_video,
    start_reconstruction,
    get_project_results,
    get_project_latest_job,
    delete_project
)
from app.api.jobs import get_job_status
from app.api.files import download_project_file
from app.core.job_manager import job_manager
from fastapi import HTTPException


class TestNormalAppWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_project_id = None
        cls.preserved_full_output = settings.BIRDS_EYE_WORKSPACE / "proj_cuda_reconstruction_full" / "outputs" / "dense_cloud.ply"
        cls.preserved_full_output_size = cls.preserved_full_output.stat().st_size if cls.preserved_full_output.exists() else None

    def tearDown(self):
        # Ensure our full reconstruction was never touched
        if self.preserved_full_output_size is not None:
            self.assertTrue(self.preserved_full_output.exists(), "proj_cuda_reconstruction_full outputs must be preserved!")
            self.assertEqual(self.preserved_full_output.stat().st_size, self.preserved_full_output_size, "proj_cuda_reconstruction_full was modified!")

    def test_01_create_and_inspect_project(self):
        req = ProjectCreateRequest(
            name="Workflow Test Project",
            description="Testing standard application lifecycle end-to-end"
        )
        created = create_project(req)
        self.assertIsNotNone(created.id)
        self.assertTrue(created.id.startswith("proj_"))
        TestNormalAppWorkflow.test_project_id = created.id

        # Verify disk directory and project.json
        p_dir = settings.BIRDS_EYE_WORKSPACE / created.id
        self.assertTrue(p_dir.exists())
        self.assertTrue((p_dir / "project.json").exists())

        # Inspect via get_project
        fetched = get_project(created.id)
        self.assertEqual(fetched.id, created.id)
        self.assertEqual(fetched.name, "Workflow Test Project")
        self.assertEqual(fetched.status, "created")
        self.assertFalse(fetched.video_uploaded)

        # Inspect in list_projects
        projects = list_projects()
        self.assertTrue(any(p.id == created.id for p in projects))

    def test_02_truthful_validation_errors(self):
        proj_id = TestNormalAppWorkflow.test_project_id
        self.assertIsNotNone(proj_id)

        # Reconstruction before video upload must fail with HTTP 400
        with self.assertRaises(HTTPException) as ctx:
            start_reconstruction(proj_id, PipelineConfigRequest())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("No video has been uploaded", ctx.exception.detail)

        # Path traversal download attempt must fail with HTTP 400
        with self.assertRaises(HTTPException) as ctx:
            download_project_file(proj_id, "../project.json")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("path traversal", ctx.exception.detail.lower())

        # Non-existent file must fail with HTTP 404
        with self.assertRaises(HTTPException) as ctx:
            download_project_file(proj_id, "non_existent_file.ply")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_03_load_video_sample(self):
        from app.api.projects import list_sample_videos
        if not any(v.get('filename') == 'test_short_clip.mp4' or v == 'test_short_clip.mp4' for v in (list_sample_videos() or [])):
            TestNormalAppWorkflow.no_sample = True
            self.skipTest('sample clip test_short_clip.mp4 not present on this machine')
        proj_id = TestNormalAppWorkflow.test_project_id
        meta = load_sample_video(proj_id, sample_name="test_short_clip.mp4")

        self.assertEqual(meta.original_filename, "test_short_clip.mp4")
        self.assertEqual(meta.filename, "source_video.mp4")
        self.assertGreater(meta.duration_seconds, 0)
        self.assertGreater(meta.frame_count, 0)
        self.assertEqual(meta.width, 1920)
        self.assertEqual(meta.height, 1080)

        # Verify project status updated
        fetched = get_project(proj_id)
        self.assertEqual(fetched.status, "video_uploaded")
        self.assertTrue(fetched.video_uploaded)
        self.assertIsNotNone(fetched.video_metadata)

    def test_04_run_workflow_reconstruction(self):
        if getattr(TestNormalAppWorkflow, 'no_sample', False):
            self.skipTest('needs the sample clip')
        proj_id = TestNormalAppWorkflow.test_project_id

        # Configure pipeline for quick, safe verification of the real workflow
        config = PipelineConfigRequest(
            sampling_fps=5.0,
            max_frames=10,
            blur_threshold=10.0,
            similarity_threshold=0.98,
            matching_strategy="exhaustive",
            enable_dense_mvs=True,
            enable_meshing=True
        )

        res = start_reconstruction(proj_id, config)
        job_id = res["job_id"]
        self.assertIsNotNone(job_id)
        self.assertEqual(res["status"], "queued")

        # Monitor progress until terminal state (timeout: 300s for full dense+mesh completion)
        start_t = time.time()
        terminal_status = None
        while time.time() - start_t < 300:
            status_obj = get_job_status(job_id)
            if status_obj.status in ("completed", "partial", "failed"):
                terminal_status = status_obj.status
                break
            time.sleep(2.0)

        self.assertIsNotNone(terminal_status, "Job did not complete within timeout")
        print(f"\n[Test Workflow] Terminal status for job {job_id}: {terminal_status}")

        final_job = get_job_status(job_id)
        # Check all pipeline stages exist (including optional AI depth densification)
        self.assertEqual(len(final_job.stages), 10)
        stage_map = {s.stage_id: s for s in final_job.stages}
        self.assertIn("validating", stage_map)
        self.assertIn("ai_depth", stage_map)
        self.assertEqual(stage_map["validating"].status, "completed")
        self.assertEqual(stage_map["extracting_frames"].status, "completed")
        self.assertEqual(stage_map["preprocessing"].status, "completed")

        # Verify project.json matches final job status
        p_obj = get_project(proj_id)
        self.assertEqual(p_obj.status, terminal_status)

        # Verify results API
        results = get_project_results(proj_id)
        self.assertEqual(results["project_id"], proj_id)
        print(f"[Test Workflow] Generated {len(results['files'])} verified output files.")

        if terminal_status in ("completed", "partial"):
            self.assertIn("sparse_cloud.ply", results["files"])
            self.assertIn("quality_report.json", results["files"])
            self.assertIsNotNone(results["quality_report"])

    def test_05_backend_restart_persistence(self):
        if getattr(TestNormalAppWorkflow, 'no_sample', False):
            self.skipTest('needs the sample clip')
        proj_id = TestNormalAppWorkflow.test_project_id

        # Read job before restart
        before_job = get_project_latest_job(proj_id)
        self.assertIsNotNone(before_job)
        job_id = before_job.job_id

        # SIMULATE BACKEND RESTART: clear all in-memory job state
        job_manager._jobs.clear()
        job_manager._cancel_flags.clear()
        self.assertEqual(len(job_manager._jobs), 0)

        # Fetch job from API after restart
        after_job = get_job_status(job_id)
        self.assertIsNotNone(after_job)
        self.assertEqual(after_job.job_id, job_id)
        self.assertEqual(after_job.status, before_job.status)
        self.assertEqual(len(after_job.stages), len(before_job.stages))

        # Test project endpoint recovery
        latest_job = get_project_latest_job(proj_id)
        self.assertIsNotNone(latest_job)
        self.assertEqual(latest_job.job_id, job_id)

    def test_06_model_viewer_file_serving(self):
        proj_id = TestNormalAppWorkflow.test_project_id
        results = get_project_results(proj_id)

        # Test downloading each available output file through download_project_file
        for filename in results["files"]:
            response = download_project_file(proj_id, filename)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(Path(response.path).exists())
            self.assertGreater(Path(response.path).stat().st_size, 0)
            print(f"[Test Workflow] Successfully served {filename} ({response.media_type})")

    @classmethod
    def tearDownClass(cls):
        # Cleanup temporary test project
        if cls.test_project_id:
            try:
                delete_project(cls.test_project_id)
                print(f"[Test Workflow] Cleaned up temporary test project {cls.test_project_id}")
            except Exception as e:
                print(f"[Test Workflow] Failed to cleanup {cls.test_project_id}: {e}")


if __name__ == "__main__":
    unittest.main()
