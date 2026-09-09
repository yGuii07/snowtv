from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EditRange:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def timeline_duration(ranges: list[EditRange]) -> float:
    return sum(item.duration for item in ranges)


def build_edit_timeline(start: float, end: float, words: list[Any], mode: str) -> list[EditRange]:
    start = max(0.0, float(start))
    end = max(start + 0.2, float(end))
    normalized_mode = (mode or "off").lower()
    if normalized_mode == "off":
        return [EditRange(start, end)]
    selected = [
        word for word in words
        if float(_value(word, "end", 0)) >= start and float(_value(word, "start", 0)) <= end
    ]
    if not selected:
        return [EditRange(start, end)]

    settings = {
        "light": (1.8, 1.0, 0.22, 0.28),
        "normal": (1.15, 0.55, 0.16, 0.22),
        "aggressive": (0.75, 0.28, 0.10, 0.16),
    }
    threshold, kept_silence, head_padding, tail_padding = settings.get(normalized_mode, settings["normal"])
    current_start = max(start, float(_value(selected[0], "start", start)) - head_padding)
    ranges: list[EditRange] = []
    for previous, current in zip(selected, selected[1:]):
        previous_end = float(_value(previous, "end", current_start))
        current_word_start = float(_value(current, "start", previous_end))
        gap = current_word_start - previous_end
        if gap <= threshold:
            continue
        range_end = min(end, previous_end + kept_silence / 2)
        if range_end - current_start >= 0.8:
            ranges.append(EditRange(current_start, range_end))
        current_start = max(start, current_word_start - kept_silence / 2)
    final_end = min(end, float(_value(selected[-1], "end", end)) + tail_padding)
    if final_end - current_start >= 0.3:
        ranges.append(EditRange(current_start, final_end))

    if not ranges or timeline_duration(ranges) < min(5.0, (end - start) * 0.45):
        trimmed_start = max(start, float(_value(selected[0], "start", start)) - head_padding)
        trimmed_end = min(end, float(_value(selected[-1], "end", end)) + tail_padding)
        return [EditRange(trimmed_start, max(trimmed_start + 0.2, trimmed_end))]
    return ranges
