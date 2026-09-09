import tempfile
import unittest
from pathlib import Path

from snow_engine.store import JobStore


class StoreTests(unittest.TestCase):
    def test_job_lifecycle_is_persistent(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "jobs.sqlite3"
            store = JobStore(database)
            store.create("a" * 32, "url", "https://youtu.be/example", {"clipCount": 3})
            store.append_log("a" * 32, "Preparando")
            store.update("a" * 32, status="completed", progress=100, result={"clips": []})
            reloaded = JobStore(database).get("a" * 32)
        self.assertEqual(reloaded["status"], "completed")
        self.assertEqual(reloaded["result"], {"clips": []})
        self.assertEqual(reloaded["logs"][0]["message"], "Preparando")

    def test_clip_feedback_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs.sqlite3")
            job_id = "c" * 32
            store.create(job_id, "url", "https://youtu.be/example", {})
            saved = store.save_feedback(job_id, 1, "good", ["other"])
            self.assertEqual(saved["rating"], "good")
            store.save_feedback(job_id, 1, "bad", ["weak_hook"])
            feedback = store.feedback(job_id)
            self.assertEqual(len(feedback), 1)
            self.assertEqual(feedback[0]["rating"], "bad")
            self.assertEqual(feedback[0]["reasons"], ["weak_hook"])

    def test_cancel_flag_survives_database_reload(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "jobs.sqlite3"
            store = JobStore(database)
            job_id = "d" * 32
            store.create(job_id, "url", "https://youtu.be/example", {})
            store.update(job_id, status="cancelled", stage="cancelled", cancel_requested=1)
            reloaded = JobStore(database).get(job_id)
            self.assertTrue(reloaded["cancel_requested"])
            self.assertEqual(reloaded["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
