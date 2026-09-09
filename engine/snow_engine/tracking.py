from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any


@dataclass(slots=True)
class TrackPoint:
    time: float
    center_x: float


@dataclass(slots=True)
class FaceTrackResult:
    points: list[TrackPoint]
    detection_samples: int
    face_samples: int
    two_face_samples: int
    split_centers: tuple[float, float] | None = None
    scene_resets: int = 0

    @property
    def two_face_ratio(self) -> float:
        return self.two_face_samples / max(1, self.detection_samples)

    @property
    def recommended_layout(self) -> str:
        # Require repeated evidence so a poster or passer-by cannot force split.
        if self.detection_samples >= 2 and self.two_face_samples >= 2 and self.two_face_ratio >= 0.5:
            return "split"
        return "track" if self.points else "center"


def _tracker_factory(cv2: Any) -> Any | None:
    factories = [
        getattr(cv2, "TrackerCSRT_create", None),
        getattr(getattr(cv2, "legacy", None), "TrackerCSRT_create", None),
        getattr(cv2, "TrackerKCF_create", None),
        getattr(getattr(cv2, "legacy", None), "TrackerKCF_create", None),
    ]
    for factory in factories:
        if callable(factory):
            try:
                return factory()
            except Exception:
                continue
    return None


def _normalize_bbox(box: Any, frame_shape: Any) -> tuple[int, int, int, int] | None:
    """Return a native-int OpenCV bbox, clipped to the current frame."""
    try:
        values = tuple(int(round(float(value))) for value in box)
    except (TypeError, ValueError, OverflowError):
        return None
    if len(values) != 4 or len(frame_shape) < 2:
        return None
    raw_x, raw_y, raw_width, raw_height = values
    frame_height = int(frame_shape[0])
    frame_width = int(frame_shape[1])
    if raw_width <= 0 or raw_height <= 0 or frame_width <= 1 or frame_height <= 1:
        return None
    left = max(0, raw_x)
    top = max(0, raw_y)
    right = min(frame_width, raw_x + raw_width)
    bottom = min(frame_height, raw_y + raw_height)
    width = right - left
    height = bottom - top
    if width <= 1 or height <= 1:
        return None
    return int(left), int(top), int(width), int(height)


def analyze_face_track(
    source: Path,
    start: float,
    end: float,
    settings: Any,
    coordinate_width: float | None = None,
    include_scene: bool = False,
) -> list[TrackPoint] | FaceTrackResult:
    import cv2

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        empty = FaceTrackResult([], 0, 0, 0)
        return empty if include_scene else empty.points
    frame_width = float(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    if frame_width <= 0:
        capture.release()
        empty = FaceTrackResult([], 0, 0, 0)
        return empty if include_scene else empty.points
    analysis_width = max(320.0, float(getattr(settings, "analysis_width", 640) or 640))
    scale = min(1.0, analysis_width / frame_width)
    output_scale = float(coordinate_width or frame_width) / frame_width
    sample_step = 1.0 / max(1.0, float(settings.face_sample_fps))
    redetect_step = max(sample_step, float(settings.face_redetect_seconds))
    cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start) * 1000)

    tracker: Any | None = None
    tracked_box: tuple[int, int, int, int] | None = None
    previous_center = frame_width / 2
    next_sample = start
    next_detection = start
    raw_points: list[TrackPoint] = []
    valid_observations = 0
    detection_samples = 0
    face_samples = 0
    two_face_samples = 0
    left_centers: list[float] = []
    right_centers: list[float] = []
    pending_switch_center: float | None = None
    pending_switch_count = 0
    previous_scene_thumb: Any | None = None
    scene_resets = 0

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        absolute_time = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0) / 1000.0
        if absolute_time > end + sample_step:
            break
        if absolute_time + 0.001 < next_sample:
            continue
        next_sample += sample_step
        if scale < 1.0:
            frame_small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            frame_small = frame

        # Scene-aware reset: a virtual camera should not carry a target from the
        # previous shot into a completely different composition. This cheap
        # thumbnail comparison only runs on sampled frames and is intentionally
        # conservative to avoid resetting on ordinary motion.
        if include_scene:
            scene_gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
            scene_thumb = cv2.resize(scene_gray, (64, 36), interpolation=cv2.INTER_AREA)
            if previous_scene_thumb is not None:
                difference = cv2.absdiff(scene_thumb, previous_scene_thumb)
                scene_score = float(difference.mean()) / 255.0
                if scene_score >= 0.30:
                    tracker = None
                    tracked_box = None
                    pending_switch_center = None
                    pending_switch_count = 0
                    next_detection = absolute_time
                    scene_resets += 1
            previous_scene_thumb = scene_thumb

        must_detect = tracker is None or absolute_time >= next_detection
        detected_box: tuple[int, int, int, int] | None = None
        if must_detect:
            detection_samples += 1
            next_detection = absolute_time + redetect_step
            gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(38, 38))
            if len(faces):
                normalized_faces = [
                    normalized
                    for face in faces
                    if (normalized := _normalize_bbox(face, frame_small.shape)) is not None
                ]
                if not normalized_faces:
                    raw_points.append(TrackPoint(max(0.0, absolute_time - start), previous_center * output_scale))
                    continue
                face_samples += 1
                horizontally_sorted = sorted(normalized_faces, key=lambda face: face[0] + face[2] / 2)
                if len(horizontally_sorted) >= 2:
                    left_face = horizontally_sorted[0]
                    right_face = horizontally_sorted[-1]
                    left_center = left_face[0] + left_face[2] / 2
                    right_center = right_face[0] + right_face[2] / 2
                    if right_center - left_center >= frame_small.shape[1] * 0.24:
                        two_face_samples += 1
                        left_centers.append(left_center / scale * output_scale)
                        right_centers.append(right_center / scale * output_scale)

                previous_small = previous_center * scale
                continuity_face = min(
                    normalized_faces,
                    key=lambda face: abs((face[0] + face[2] / 2) - previous_small),
                )
                largest_face = max(normalized_faces, key=lambda face: face[2] * face[3])
                chosen = continuity_face
                if valid_observations == 0:
                    chosen = largest_face
                elif largest_face != continuity_face:
                    continuity_area = max(1, continuity_face[2] * continuity_face[3])
                    largest_center = largest_face[0] + largest_face[2] / 2
                    if largest_face[2] * largest_face[3] >= continuity_area * 1.45:
                        if pending_switch_center is not None and abs(largest_center - pending_switch_center) <= frame_small.shape[1] * 0.1:
                            pending_switch_count += 1
                        else:
                            pending_switch_center = largest_center
                            pending_switch_count = 1
                        if pending_switch_count >= 2:
                            chosen = largest_face
                            pending_switch_center = None
                            pending_switch_count = 0
                    else:
                        pending_switch_center = None
                        pending_switch_count = 0
                else:
                    pending_switch_center = None
                    pending_switch_count = 0

                detected_box = chosen
                if detected_box is not None:
                    tracker = _tracker_factory(cv2)
                    if tracker is not None:
                        try:
                            tracker.init(frame_small, detected_box)
                        except Exception:
                            tracker = None
                    tracked_box = detected_box
        elif tracker is not None:
            try:
                tracked_ok, box = tracker.update(frame_small)
            except Exception:
                tracked_ok, box = False, None
            normalized_box = _normalize_bbox(box, frame_small.shape) if tracked_ok else None
            if normalized_box is not None:
                tracked_box = normalized_box
            else:
                tracker = None
                tracked_box = None

        active_box = detected_box or tracked_box
        if active_box is not None:
            x, _, width, _ = active_box
            center = (x + width / 2) / scale
            previous_center = max(0.0, min(frame_width, center))
            valid_observations += 1
        raw_points.append(TrackPoint(max(0.0, absolute_time - start), previous_center * output_scale))

    capture.release()
    split_centers = (
        (float(median(left_centers)), float(median(right_centers)))
        if left_centers and right_centers
        else None
    )
    if not raw_points or valid_observations < 2:
        result = FaceTrackResult([], detection_samples, face_samples, two_face_samples, split_centers, scene_resets)
        return result if include_scene else result.points

    smoothed: list[TrackPoint] = []
    center = raw_points[0].center_x
    previous_time = raw_points[0].time
    frame_limit = float(coordinate_width or frame_width)
    for point in raw_points:
        elapsed = max(sample_step, point.time - previous_time)
        difference = point.center_x - center
        dead_zone = frame_limit * 0.012
        if abs(difference) < dead_zone:
            difference = 0.0
        maximum_shift = frame_limit * 0.22 * elapsed
        difference = max(-maximum_shift, min(maximum_shift, difference))
        center += difference * 0.28
        previous_time = point.time
        smoothed.append(TrackPoint(point.time, center))

    compact: list[TrackPoint] = []
    for point in smoothed:
        if not compact or point.time - compact[-1].time >= 0.65:
            compact.append(point)
    if compact[-1].time < smoothed[-1].time:
        compact.append(smoothed[-1])
    result = FaceTrackResult(compact, detection_samples, face_samples, two_face_samples, split_centers, scene_resets)
    return result if include_scene else result.points


def crop_x_expression(points: list[TrackPoint], frame_width: int, crop_width: int) -> str:
    maximum_x = max(0.0, float(frame_width - crop_width))

    def x_at(point: TrackPoint) -> float:
        return max(0.0, min(maximum_x, point.center_x - crop_width / 2))

    if not points:
        return f"{maximum_x / 2:.3f}"
    expression = f"{x_at(points[-1]):.3f}"
    for current, following in reversed(list(zip(points, points[1:]))):
        delta = max(0.001, following.time - current.time)
        current_x = x_at(current)
        change = x_at(following) - current_x
        linear = f"{current_x:.3f}+({change:.3f})*(t-{current.time:.3f})/{delta:.3f}"
        expression = f"if(lt(t,{following.time:.3f}),{linear},{expression})"
    return expression
