import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    from snow_engine import api
    from snow_engine.store import JobStore
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False


class DummyQueue:
    def __init__(self, store):
        self.store = store

    def cancel(self, job_id):
        job = self.store.get(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return False
        self.store.update(job_id, status="cancelled", stage="cancelled", progress=100, cancel_requested=1)
        return True

    def resume(self, job_id):
        job = self.store.get(job_id)
        if job["status"] not in {"cancelled", "failed"}:
            raise ValueError("estado inválido")
        self.store.update(job_id, status="queued", stage="queued", progress=0, cancel_requested=0)


@unittest.skipUnless(API_AVAILABLE, "FastAPI/pydantic-settings não instalados neste ambiente")
class ApiTests(unittest.TestCase):
    def test_cors_allows_local_vite_ports(self):
        client = TestClient(api.app)
        for origin in (
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:6182",
            "http://[::1]:5173",
        ):
            with self.subTest(origin=origin):
                response = client.options(
                    "/health",
                    headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("access-control-allow-origin"), origin)

    def test_cors_does_not_open_unlisted_remote_origins(self):
        client = TestClient(api.app)
        response = client.options(
            "/health",
            headers={"Origin": "http://example.com", "Access-Control-Request-Method": "GET"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(response.headers.get("access-control-allow-origin"))

    def test_cancel_and_resume_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs.sqlite3")
            job_id = "e" * 32
            store.create(job_id, "url", "https://youtu.be/example", {})
            queue = DummyQueue(store)
            with patch.object(api, "store", store), patch.object(api, "queue", queue):
                client = TestClient(api.app)
                cancelled = client.post(f"/api/jobs/{job_id}/cancel")
                self.assertEqual(cancelled.status_code, 200)
                self.assertEqual(cancelled.json()["status"], "cancelled")
                resumed = client.post(f"/api/jobs/{job_id}/resume")
                self.assertEqual(resumed.status_code, 202)
                self.assertEqual(resumed.json()["job_id"], job_id)

    def test_rejects_invalid_job_identifier(self):
        client = TestClient(api.app)
        self.assertEqual(client.post("/api/jobs/not-valid/cancel").status_code, 400)


if __name__ == "__main__":
    unittest.main()
