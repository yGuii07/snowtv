import unittest

from snow_engine.tracking import FaceTrackResult, TrackPoint, _normalize_bbox, crop_x_expression


class TrackingTests(unittest.TestCase):
    def test_persistent_two_faces_recommend_split(self):
        result = FaceTrackResult(
            points=[TrackPoint(0.0, 200), TrackPoint(1.0, 210)],
            detection_samples=6,
            face_samples=6,
            two_face_samples=4,
            split_centers=(150, 490),
        )

        self.assertEqual(result.recommended_layout, "split")

    def test_brief_second_face_keeps_tracking(self):
        result = FaceTrackResult(
            points=[TrackPoint(0.0, 200), TrackPoint(1.0, 210)],
            detection_samples=6,
            face_samples=6,
            two_face_samples=1,
        )

        self.assertEqual(result.recommended_layout, "track")

    def test_bbox_is_clipped_and_converted_to_native_int_tuple(self):
        box = _normalize_bbox((-4.7, 12.2, 105.8, 80.4), (720, 1280, 3))

        self.assertEqual(box, (0, 12, 101, 80))
        self.assertIsInstance(box, tuple)
        self.assertTrue(all(type(value) is int for value in box))

    def test_invalid_bboxes_are_rejected(self):
        self.assertIsNone(_normalize_bbox((10, 10, 0, 30), (720, 1280, 3)))
        self.assertIsNone(_normalize_bbox((10, 10, -5, 30), (720, 1280, 3)))
        self.assertIsNone(_normalize_bbox((2000, 10, 30, 30), (720, 1280, 3)))
        self.assertIsNone(_normalize_bbox(None, (720, 1280, 3)))

    def test_empty_track_uses_exact_central_crop(self):
        self.assertEqual(crop_x_expression([], frame_width=1920, crop_width=1080), "420.000")


if __name__ == "__main__":
    unittest.main()
