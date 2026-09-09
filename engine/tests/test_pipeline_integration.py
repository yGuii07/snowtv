import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from snow_engine.pipeline import Pipeline
from snow_engine.selector import HighlightSelector
from snow_engine.store import JobStore
from snow_engine.tracking import FaceTrackResult, TrackPoint
from snow_engine.transcription import Transcript, Word


class FakeTranscriber:
    def __init__(self):
        self.calls = 0

    def transcribe(self, _audio, _language, _profile, progress_callback=None):
        self.calls += 1
        if progress_callback:
            progress_callback(0.5)
            progress_callback(1.0)
        words = []
        vocabulary = ["Você", "precisa", "entender", "este", "segredo", "porque", "muda", "tudo."]
        for index in range(24):
            start = 0.2 + index * 0.29
            words.append(Word(start, start + 0.22, vocabulary[index % len(vocabulary)], 0.95))
        return Transcript("pt", 0.99, 8.0, " ".join(item.word for item in words), words)


def make_test_settings(root: Path):
    return SimpleNamespace(
        jobs_dir=root / "jobs",
        resolved_cache_dir=root / "cache",
        cache_enabled=True,
        max_video_minutes=30,
        performance_profile="auto",
        whisper_model="auto",
        whisper_device="cpu",
        whisper_compute_type="auto",
        whisper_cpu_threads=0,
        analysis_width=0,
        video_preset="auto",
        video_encoder="auto",
        video_crf=0,
        llm_provider="heuristic",
        llm_model="",
    )


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg não disponível")
class PipelineIntegrationTests(unittest.TestCase):
    def test_upload_render_tracking_fallback_and_transcript_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = make_test_settings(root)
            settings.jobs_dir.mkdir(parents=True)
            source = root / "uploaded.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=20",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=16000",
                    "-t", "8", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-shortest", str(source),
                ],
                check=True,
            )
            store = JobStore(root / "jobs.sqlite3")
            transcriber = FakeTranscriber()
            pipeline = Pipeline(settings, store, transcriber, HighlightSelector(settings))
            base_options = {
                "language": "pt",
                "duration": "auto",
                "clipCount": 1,
                "performanceProfile": "eco",
                "captions": True,
                "pauseRemoval": "off",
                "hookMode": "auto",
                "captionStyle": {"preset": "minimal"},
            }

            first_id = "a" * 32
            store.create(first_id, "upload", "uploaded.mp4", {**base_options, "layout": "track"}, str(source))
            with patch("snow_engine.pipeline.analyze_face_track", side_effect=RuntimeError("tracker unavailable")):
                pipeline.process(first_id)
            first = store.get(first_id)
            self.assertEqual(first["status"], "completed")
            self.assertEqual(first["result"]["clips"][0]["layout"], "center")
            self.assertTrue((settings.jobs_dir / first_id / "clips" / "clip-01.mp4").is_file())
            self.assertTrue(any("crop central" in item["message"] for item in first["logs"]))

            second_id = "b" * 32
            store.create(
                second_id,
                "upload",
                "uploaded.mp4",
                {**base_options, "layout": "center", "captions": False, "hookMode": "off"},
                str(source),
            )
            pipeline.process(second_id)
            second = store.get(second_id)
            self.assertEqual(second["status"], "completed")
            self.assertTrue(second["result"]["cache"]["transcript"])
            self.assertEqual(transcriber.calls, 1)
            self.assertIn("render", second["result"]["timings"])
            self.assertFalse((settings.jobs_dir / second_id / "captions-01.ass").exists())

            third_id = "c" * 32
            store.create(third_id, "upload", "uploaded.mp4", {**base_options, "layout": "track"}, str(source))
            tracked = FaceTrackResult([TrackPoint(0, 320), TrackPoint(6, 340)], 4, 4, 0)
            with patch("snow_engine.pipeline.analyze_face_track", return_value=tracked) as analyzer:
                pipeline.process(third_id)
                self.assertEqual(analyzer.call_count, 1)
            self.assertFalse(store.get(third_id)["result"]["cache"]["tracking"])

            fourth_id = "d" * 32
            store.create(fourth_id, "upload", "uploaded.mp4", {**base_options, "layout": "track"}, str(source))
            with patch("snow_engine.pipeline.analyze_face_track", side_effect=AssertionError("tracking cache missed")):
                pipeline.process(fourth_id)
            fourth = store.get(fourth_id)
            self.assertEqual(fourth["status"], "completed")
            self.assertTrue(fourth["result"]["cache"]["tracking"])
            self.assertEqual(fourth["result"]["cache"]["tracking_hits"], 1)
        self.assertFalse(root.exists(), "Temporary pipeline workspace was not cleaned")


if __name__ == "__main__":
    unittest.main()
