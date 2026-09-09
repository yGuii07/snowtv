import tempfile
import unittest
from pathlib import Path

from snow_engine.cache import CacheManager


class CacheTests(unittest.TestCase):
    def test_reuses_source_and_json_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.mp4"
            source.write_bytes(b"snow-video-content")
            cache = CacheManager(root / "cache")
            registered = cache.register_source(source, "https://youtu.be/example", "url")
            looked_up = cache.source_for_url("https://youtu.be/example")
            self.assertIsNotNone(looked_up)
            self.assertEqual(looked_up.content_hash, registered.content_hash)
            materialized = cache.materialize_source(looked_up, root / "job")
            self.assertEqual(materialized.read_bytes(), source.read_bytes())

            transcript_path = cache.transcript_path(registered.content_hash, "pt", "small")
            cache.save_json(transcript_path, {"words": [{"word": "teste"}]})
            self.assertEqual(cache.load_json(transcript_path)["words"][0]["word"], "teste")

            tracking_path = cache.tracking_path(registered.content_hash, {"start": 1.0, "end": 4.0})
            cache.save_json(tracking_path, {"kind": "points", "points": []})
            self.assertEqual(cache.load_json(tracking_path)["kind"], "points")


if __name__ == "__main__":
    unittest.main()
