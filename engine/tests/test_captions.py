import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from snow_engine.captions import write_ass


class CaptionTests(unittest.TestCase):
    def test_writes_highlighted_ass_captions(self):
        words = [
            SimpleNamespace(start=10.0, end=10.4, word="o"),
            SimpleNamespace(start=10.5, end=11.0, word="segredo"),
            SimpleNamespace(start=11.1, end=11.5, word="é"),
            SimpleNamespace(start=11.6, end=12.0, word="começar."),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ass(Path(temporary) / "captions.ass", words, 10, 14, "O melhor começo")
            content = path.read_text(encoding="utf-8")
        self.assertIn("Style: Caption", content)
        self.assertIn("O MELHOR COMEÇO", content)
        self.assertIn("&H005FD6FF", content)

    def test_bounce_preset_and_safe_zone_are_rendered(self):
        words = [SimpleNamespace(start=1.0, end=1.4, word="impacto")]
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ass(
                Path(temporary) / "bounce.ass",
                words,
                1,
                2,
                None,
                style={"preset": "bounce", "safeZone": "tiktok", "position": 82},
            )
            content = path.read_text(encoding="utf-8")
        self.assertIn("\\fscx116", content)
        self.assertIn("Style: Caption", content)
        self.assertIn(",360,1", content)

    def test_scale_animation_is_supported(self):
        words = [SimpleNamespace(start=1.0, end=1.4, word="agora")]
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ass(
                Path(temporary) / "scale.ass", words, 1, 2, None,
                style={"preset": "bold", "animation": "scale"},
            )
            content = path.read_text(encoding="utf-8")
        self.assertIn("\\fscx112", content)

    def test_long_caption_is_wrapped_with_horizontal_safe_area(self):
        texts = ["contrário,", "talvez", "seja", "necessário", "continuar", "outros", "projetos"]
        words = [
            SimpleNamespace(start=index * .35, end=index * .35 + .28, word=text)
            for index, text in enumerate(texts)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ass(
                Path(temporary) / "safe-caption.ass",
                words,
                0,
                4,
                None,
                style={"preset": "karaoke", "maxWords": 10, "maxLines": 2},
            )
            content = path.read_text(encoding="utf-8")
        self.assertIn("WrapStyle: 0", content)
        self.assertIn(",108,108,", content)
        caption_events = [line for line in content.splitlines() if ",Caption," in line]
        self.assertTrue(caption_events)
        self.assertTrue(all(event.count(r"\N") <= 1 for event in caption_events))
        self.assertTrue(any(r"\N" in event for event in caption_events))


    def test_hook_hides_regular_captions_until_hook_finishes(self):
        words = [
            SimpleNamespace(start=0.0, end=0.6, word="dois"),
            SimpleNamespace(start=0.7, end=1.3, word="ate"),
            SimpleNamespace(start=1.4, end=2.0, word="hoje"),
            SimpleNamespace(start=4.0, end=4.6, word="mudou"),
            SimpleNamespace(start=4.7, end=5.2, word="tudo"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ass(
                Path(temporary) / "hook-priority.ass",
                words,
                0,
                6,
                "Ate hoje",
            )
            content = path.read_text(encoding="utf-8")

        hook_event = next(line for line in content.splitlines() if ",Hook," in line)
        caption_events = [line for line in content.splitlines() if ",Caption," in line]
        self.assertIn("0:00:04.20", hook_event)
        self.assertTrue(caption_events)
        self.assertTrue(all(",0:00:04.20," in event or event.split(",")[2] >= "0:00:04.20" for event in caption_events[:1]))
        self.assertNotIn("DOIS", "\n".join(caption_events))
        self.assertNotIn("ATE", "\n".join(caption_events))

    def test_long_hook_is_bounded_to_two_lines(self):
        title = "Minha história talvez tenha algum exemplo completamente diferente e muito longo para a tela vertical"
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ass(Path(temporary) / "safe-hook.ass", [], 0, 8, title)
            content = path.read_text(encoding="utf-8")
        hook_event = next(line for line in content.splitlines() if ",Hook," in line)
        self.assertEqual(hook_event.count(r"\N"), 1)
        self.assertIn("…", hook_event)
        self.assertNotIn("PARA A TELA VERTICAL", hook_event)


if __name__ == "__main__":
    unittest.main()
