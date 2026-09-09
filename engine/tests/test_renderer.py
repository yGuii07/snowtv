import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from snow_engine.captions import write_ass
from snow_engine.editing import EditRange
from snow_engine.hardware import PerformancePreset
from snow_engine.media import probe, render_clip

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover - optional test-only image inspection
    np = None
    Image = None


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg não disponível")
class RendererIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(Image is not None and np is not None, "Pillow/NumPy não disponíveis")
    def test_long_ass_text_stays_inside_vertical_safe_width(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            texts = "ao contrário talvez seja até mais importante continuar seguindo outros projetos completamente diferentes".split()
            words = [
                SimpleNamespace(start=index * .4, end=index * .4 + .32, word=text)
                for index, text in enumerate(texts)
            ]
            ass = write_ass(
                root / "safe.ass",
                words,
                0,
                8,
                "Minha história talvez tenha algum exemplo completamente diferente e muito longo para a tela vertical",
                width=1080,
                height=1920,
                style={"preset": "karaoke", "maxWords": 10, "maxLines": 2},
            )
            for index, timestamp in enumerate((.8, 4.1)):
                frame_path = root / f"frame-{index}.png"
                subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=0x58738c:s=1080x1920:d=6:r=30",
                        "-vf", f"ass={ass}", "-ss", str(timestamp), "-frames:v", "1", str(frame_path),
                    ],
                    check=True,
                )
                frame = np.asarray(Image.open(frame_path).convert("RGB"))
                background = frame[900, 40].astype(np.int16)
                mask = np.max(np.abs(frame.astype(np.int16) - background), axis=2) > 45
                _, x_positions = np.where(mask)
                self.assertGreater(len(x_positions), 100)
                self.assertGreaterEqual(int(x_positions.min()), 70)
                self.assertLessEqual(int(x_positions.max()), 1009)

    def test_renders_captioned_jump_cut_mp4(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-t", "4", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-shortest", str(source),
                ],
                check=True,
            )
            words = [
                SimpleNamespace(start=0.2, end=0.7, word="PRIMEIRO"),
                SimpleNamespace(start=0.8, end=1.2, word="MOMENTO"),
                SimpleNamespace(start=2.2, end=2.7, word="SEGUNDO"),
                SimpleNamespace(start=2.8, end=3.2, word="MOMENTO"),
            ]
            timeline = [EditRange(0, 1.4), EditRange(2, 3.4)]
            ass = write_ass(
                root / "captions.ass",
                words,
                0,
                3.4,
                "TESTE REAL",
                width=360,
                height=640,
                style={"preset": "bounce", "safeZone": "shorts"},
                timeline=timeline,
            )
            profile = PerformancePreset(
                "test", "small", "int8", 2, 2, 480, 2, 1.5,
                "libx264", "ultrafast", 25, 360, 640, 24, 3,
            )
            output = root / "clip.mp4"
            render_clip(
                source,
                output,
                ass,
                0,
                3.4,
                "center",
                probe(source),
                [],
                SimpleNamespace(),
                profile=profile,
                timeline=timeline,
            )
            metadata = probe(output)
            self.assertTrue(output.stat().st_size > 1000)
            self.assertEqual((metadata["width"], metadata["height"]), (360, 640))
            self.assertGreater(metadata["duration"], 2.5)
            self.assertLess(metadata["duration"], 3.2)


if __name__ == "__main__":
    unittest.main()
