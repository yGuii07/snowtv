import unittest
from types import SimpleNamespace
from unittest.mock import patch

from snow_engine.hardware import resolve_profile


class HardwareTests(unittest.TestCase):
    def test_ryzen_4600g_auto_uses_balanced_cpu_int8(self):
        settings = SimpleNamespace(
            performance_profile="auto",
            whisper_model="auto",
            whisper_compute_type="auto",
            whisper_cpu_threads=0,
            analysis_width=0,
            video_preset="auto",
            video_encoder="auto",
            video_crf=0,
        )
        hardware = {
            "cpu": "AMD Ryzen 5 4600G with Radeon Graphics",
            "logical_cores": 12,
            "ram_gb": 15.9,
            "target_ryzen_4600g": True,
        }
        with patch("snow_engine.hardware.detect_hardware", return_value=hardware):
            profile = resolve_profile(settings, "auto")
        self.assertEqual(profile.name, "balanced")
        self.assertEqual(profile.whisper_model, "small")
        self.assertEqual(profile.compute_type, "int8")
        self.assertEqual(profile.cpu_threads, 8)
        self.assertEqual(profile.encoder, "libx264")


if __name__ == "__main__":
    unittest.main()
