import unittest

from snow_engine.models import ProcessOptions


class ModelTests(unittest.TestCase):
    def test_process_options_accept_editorial_style_and_clip_override(self):
        options = ProcessOptions.model_validate({
            "editorialStyle": "podcast",
            "clipOverrides": [{"index": 1, "start": 12.5, "end": 42.0, "title": "Novo título"}],
            "captionStyle": {"animation": "scale"},
        })
        self.assertEqual(options.editorial_style, "podcast")
        self.assertEqual(options.clip_overrides[0].start, 12.5)
        self.assertEqual(options.caption_style.animation, "scale")


if __name__ == "__main__":
    unittest.main()
