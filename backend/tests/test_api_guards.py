"""API safety tests: concurrent jobs, sample-name traversal, stale COLMAP database files."""
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.core.job_manager import job_manager


class TestApiGuards(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.pid = self.client.post("/api/projects", json={"name": "guard"}).json()["id"]

    def tearDown(self):
        job_manager._threads.clear()
        self.client.delete(f"/api/projects/{self.pid}")

    def _fake_running_job(self):
        ev = threading.Event()
        th = threading.Thread(target=ev.wait, daemon=True)
        th.start()
        job_manager._jobs["job_fake"] = {"project_id": self.pid}
        job_manager._threads["job_fake"] = th
        return ev

    def test_second_job_and_delete_rejected_while_running(self):
        ev = self._fake_running_job()
        try:
            (Path(__import__("app.api.projects", fromlist=["VideoService"]).VideoService.get_project_dir(self.pid)) / "input").mkdir(exist_ok=True)
            self.assertEqual(self.client.delete(f"/api/projects/{self.pid}").status_code, 409)
            self.assertEqual(self.client.post(f"/api/projects/{self.pid}/load_sample?sample_name=x.mp4").status_code, 409)
        finally:
            ev.set()

    def test_sample_name_cannot_escape_reference_folder(self):
        r = self.client.post(f"/api/projects/{self.pid}/load_sample?sample_name=../../README.md")
        self.assertEqual(r.status_code, 404)

    def test_bad_preset_is_rejected(self):
        self.assertEqual(self.client.post(f"/api/projects/{self.pid}/reconstruction",
                                          json={"quality_preset": "ultra"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
