import tempfile
import threading
import time
import unittest
from pathlib import Path

from snow_engine.queue import JobQueue
from snow_engine.store import JobStore


class FakePipeline:
    def __init__(self, event):
        self.event = event

    def process(self, _job_id):
        self.event.set()


class BlockingPipeline:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.resumed = threading.Event()
        self.calls = 0

    def process(self, _job_id):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            self.release.wait(2)
        else:
            self.resumed.set()


class QueueRecoveryTests(unittest.TestCase):
    def test_recovers_persisted_queued_job_after_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs.sqlite3")
            job_id = "c" * 32
            store.create(job_id, "url", "https://youtu.be/example", {"clipCount": 1})
            event = threading.Event()
            queue = JobQueue(store, FakePipeline(event), workers=1)
            recovered = queue.recover()
            self.assertEqual(recovered, 1)
            self.assertTrue(event.wait(2))
            self.assertTrue(any("recuperada" in item["message"].lower() for item in store.get(job_id)["logs"]))
            queue.shutdown()

    def test_cancel_and_resume_persisted_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs.sqlite3")
            job_id = "d" * 32
            store.create(job_id, "url", "https://youtu.be/example", {"clipCount": 1})
            pipeline = BlockingPipeline()
            queue = JobQueue(store, pipeline, workers=1)
            queue.submit(job_id)
            self.assertTrue(pipeline.started.wait(1))
            self.assertTrue(queue.cancel(job_id))
            self.assertEqual(store.get(job_id)["status"], "cancelled")
            self.assertTrue(store.get(job_id)["cancel_requested"])
            pipeline.release.set()
            for _ in range(50):
                if not queue._active:
                    break
                time.sleep(.01)
            queue.resume(job_id)
            self.assertTrue(pipeline.resumed.wait(1))
            self.assertEqual(store.get(job_id)["status"], "queued")
            self.assertFalse(store.get(job_id)["cancel_requested"])
            queue.shutdown()


if __name__ == "__main__":
    unittest.main()
