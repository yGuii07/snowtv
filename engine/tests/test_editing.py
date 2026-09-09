import unittest
from types import SimpleNamespace

from snow_engine.editing import build_edit_timeline, timeline_duration


class EditingTests(unittest.TestCase):
    def test_off_preserves_original_timeline(self):
        ranges = build_edit_timeline(5, 20, [], "off")
        self.assertEqual([(item.start, item.end) for item in ranges], [(5, 20)])

    def test_normal_removes_only_long_internal_pause(self):
        words = [
            SimpleNamespace(start=0.2, end=0.7, word="começo"),
            SimpleNamespace(start=0.8, end=1.2, word="natural"),
            SimpleNamespace(start=3.8, end=4.2, word="volta"),
            SimpleNamespace(start=4.3, end=5.0, word="completa."),
        ]
        ranges = build_edit_timeline(0, 6, words, "normal")
        self.assertEqual(len(ranges), 2)
        self.assertLess(timeline_duration(ranges), 4.0)
        self.assertGreater(timeline_duration(ranges), 2.0)


if __name__ == "__main__":
    unittest.main()
