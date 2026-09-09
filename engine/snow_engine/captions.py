from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from itertools import combinations
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CaptionPreset:
    key: str
    name: str
    font: str
    size: int
    bold: int
    uppercase: bool
    primary: str
    highlight: str
    outline: str
    outline_width: int
    shadow: int
    background: bool
    animation: str
    spacing: float = 0


CAPTION_PRESETS: dict[str, CaptionPreset] = {
    "none": CaptionPreset("none", "Sem legenda", "Arial", 66, -1, False, "#FFFFFF", "#FFD65F", "#101822", 0, 0, False, "none"),
    "karaoke": CaptionPreset("karaoke", "Snow Karaoke", "Arial", 70, -1, True, "#FFFFFF", "#FFD65F", "#101822", 8, 2, False, "karaoke"),
    "bold": CaptionPreset("bold", "Snow Beast", "Arial", 76, -1, True, "#FFFFFF", "#61D7FF", "#08121E", 10, 3, False, "pop"),
    "minimal": CaptionPreset("minimal", "Snow Clean", "Arial", 58, 0, False, "#FFFFFF", "#BFEFFF", "#101820", 3, 1, False, "none"),
    "podcast": CaptionPreset("podcast", "Snow Podcast", "Arial", 64, -1, False, "#FFFFFF", "#FFD65F", "#07111D", 5, 1, True, "karaoke"),
    "highlight": CaptionPreset("highlight", "Snow Focus", "Arial", 70, -1, True, "#FFFFFF", "#8FF1C1", "#091521", 8, 2, False, "karaoke"),
    "bounce": CaptionPreset("bounce", "Snow Bounce", "Arial", 72, -1, True, "#FFFFFF", "#FF7CC8", "#0A1420", 8, 3, False, "bounce"),
    "pop": CaptionPreset("pop", "Snow Popline", "Arial", 74, -1, True, "#FFFFFF", "#FF8A65", "#09131F", 9, 3, False, "pop"),
    "deep": CaptionPreset("deep", "Snow Deep Diver", "Arial", 66, -1, False, "#EAF6FF", "#5FD6FF", "#07111C", 6, 2, True, "karaoke", 1.0),
    "glitch": CaptionPreset("glitch", "Snow Glitch", "Arial", 70, -1, True, "#FFFFFF", "#5FFFE4", "#32125F", 7, 2, False, "glitch", 1.5),
}

SEMANTIC_TERMS = {
    "erro", "segredo", "nunca", "sempre", "verdade", "dinheiro", "resultado", "atenção",
    "importante", "problema", "solução", "melhor", "pior", "mistake", "secret", "never",
    "always", "truth", "money", "result", "important", "problem", "solution", "best", "worst",
}


def caption_presets_payload() -> list[dict[str, Any]]:
    return [asdict(value) for value in CAPTION_PRESETS.values()]


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _ass_color(value: str, alpha: int = 0) -> str:
    clean = value.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", clean):
        clean = "FFFFFF"
    red, green, blue = clean[0:2], clean[2:4], clean[4:6]
    return f"&H{max(0, min(255, alpha)):02X}{blue.upper()}{green.upper()}{red.upper()}"


def _style_value(style: Any, name: str, default: Any = None) -> Any:
    if style is None:
        return default
    if isinstance(style, dict):
        return style.get(name, default)
    return getattr(style, name, default)


def _resolved_preset(style: Any) -> CaptionPreset:
    key = str(_style_value(style, "preset", "karaoke") or "karaoke").lower()
    preset = CAPTION_PRESETS.get(key, CAPTION_PRESETS["karaoke"])
    weight = str(_style_value(style, "weight", "black") or "black")
    return replace(
        preset,
        font=str(_style_value(style, "font", preset.font) or preset.font)[:80],
        size=int(_style_value(style, "size", None) or preset.size),
        bold=0 if weight == "normal" else -1,
        uppercase=preset.uppercase if _style_value(style, "uppercase", None) is None else bool(_style_value(style, "uppercase")),
        primary=str(_style_value(style, "primary_color", None) or _style_value(style, "primaryColor", None) or preset.primary),
        highlight=str(_style_value(style, "highlight_color", None) or _style_value(style, "highlightColor", None) or preset.highlight),
        outline=str(_style_value(style, "outline_color", None) or _style_value(style, "outlineColor", None) or preset.outline),
        outline_width=int(_style_value(style, "outline", None) if _style_value(style, "outline", None) is not None else preset.outline_width),
        shadow=int(_style_value(style, "shadow", None) if _style_value(style, "shadow", None) is not None else preset.shadow),
        background=preset.background if _style_value(style, "background", None) is None else bool(_style_value(style, "background")),
        animation=str(_style_value(style, "animation", None) or preset.animation),
        spacing=float(_style_value(style, "spacing", preset.spacing) or 0),
    )


def _mapped_words(words: list[Any], clip_start: float, clip_end: float, timeline: list[Any] | None) -> list[dict[str, Any]]:
    ranges = timeline or [{"start": clip_start, "end": clip_end}]
    mapped: list[dict[str, Any]] = []
    elapsed = 0.0
    for item in ranges:
        range_start = float(_value(item, "start", clip_start))
        range_end = float(_value(item, "end", clip_end))
        for word in words:
            word_start = float(_value(word, "start", 0))
            word_end = float(_value(word, "end", word_start))
            if word_end < range_start or word_start > range_end:
                continue
            start = elapsed + max(0.0, word_start - range_start)
            end = elapsed + min(range_end - range_start, max(0.0, word_end - range_start))
            if end <= start:
                end = start + 0.08
            mapped.append({
                "start": start,
                "end": end,
                "word": str(_value(word, "word", "")).strip(),
                "probability": float(_value(word, "probability", 1.0) or 0.0),
            })
        elapsed += max(0.0, range_end - range_start)
    unique: list[dict[str, Any]] = []
    for item in sorted(mapped, key=lambda value: (value["start"], value["end"])):
        if item["word"] and (not unique or (item["start"], item["word"]) != (unique[-1]["start"], unique[-1]["word"])):
            unique.append(item)
    return unique


def _caption_groups(words: list[Any], max_words: int, max_lines: int) -> list[list[Any]]:
    return _caption_groups_for_width(words, max_words, max_lines, 22.0)


def _display_units(text: str) -> float:
    """Estimate rendered width without depending on a platform font backend."""
    narrow = set(" .,:;!|'ijlI1")
    wide = set("MWQG@%mw")
    return sum(0.48 if character in narrow else 1.35 if character in wide else 1.0 for character in text)


def _caption_groups_for_width(
    words: list[Any],
    max_words: int,
    max_lines: int,
    max_units_per_line: float,
) -> list[list[Any]]:
    groups: list[list[Any]] = []
    current: list[Any] = []
    for word in words:
        text = str(_value(word, "word", "")).strip()
        if not text:
            continue
        gap = 0.0 if not current else float(_value(word, "start", 0)) - float(_value(current[-1], "end", 0))
        candidate_texts = [str(_value(item, "word", "")).strip() for item in current] + [text]
        candidate_lines = _balanced_lines(candidate_texts, max_lines, max_units_per_line)
        candidate_fits = all(
            _display_units(" ".join(candidate_texts[index] for index in line)) <= max_units_per_line
            for line in candidate_lines
        )
        if current and (len(current) >= max_words or not candidate_fits or gap > 0.58):
            groups.append(current)
            current = []
        current.append(word)
        if text.endswith((".", "!", "?", "…", ":", ";")) and len(current) >= 2:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _balanced_lines(texts: list[str], max_lines: int, max_units_per_line: float) -> list[list[int]]:
    """Split a short phrase into balanced, bounded, contiguous lines."""
    if not texts:
        return []
    maximum_lines = max(1, min(max_lines, len(texts)))
    best: tuple[tuple[float, float, float, int], list[list[int]]] | None = None
    for line_count in range(1, maximum_lines + 1):
        for cuts in combinations(range(1, len(texts)), line_count - 1):
            boundaries = (0, *cuts, len(texts))
            lines = [list(range(boundaries[index], boundaries[index + 1])) for index in range(line_count)]
            widths = [_display_units(" ".join(texts[index] for index in line)) for line in lines]
            overflow = sum(max(0.0, width - max_units_per_line) ** 2 for width in widths)
            raggedness = max(widths) - min(widths)
            score = (1.0 if overflow else 0.0, overflow, max(widths), line_count * 0.05 + raggedness)
            if best is None or score < best[0]:
                best = (score, lines)
        if best is not None and best[0][0] == 0.0:
            break
    return best[1] if best else [list(range(len(texts)))]


def _compact_wrapped_text(text: str, max_lines: int, max_units_per_line: float) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return ""
    words = clean.split()
    capacity = max_lines * max_units_per_line
    kept: list[str] = []
    used = 0.0
    truncated = False
    for word in words:
        added = _display_units(word) + (1.0 if kept else 0.0)
        if kept and used + added > capacity:
            truncated = True
            break
        kept.append(word)
        used += added
    if truncated and kept:
        ellipsis = "…"
        while len(kept) > 1 and _display_units(" ".join(kept) + ellipsis) > capacity:
            kept.pop()
        kept[-1] = kept[-1].rstrip(".,;:!?…") + ellipsis
    lines = _balanced_lines(kept, max_lines, max_units_per_line)
    return "\n".join(" ".join(kept[index] for index in line) for line in lines)


def _active_word(text: str, preset: CaptionPreset, semantic: bool, active: bool) -> str:
    rendered = _escape(text.upper() if preset.uppercase else text)
    important = semantic and re.sub(r"[^\wÀ-ÿ]", "", text.lower()) in SEMANTIC_TERMS
    if not active and not important:
        return rendered
    color = _ass_color(preset.highlight)
    if not active:
        return rf"{{\c{color}}}{rendered}{{\c{_ass_color(preset.primary)}}}"
    animation = preset.animation
    extra = ""
    if animation == "bounce":
        extra = r"\fscx116\fscy116\t(0,140,\fscx100\fscy100)"
    elif animation == "pop":
        extra = r"\fscx108\fscy108\t(0,100,\fscx100\fscy100)"
    elif animation == "glitch":
        extra = r"\frz-2\fscx106\t(0,100,\frz2\fscx100)"
    elif animation == "scale":
        extra = r"\fscx112\fscy112\t(0,160,\fscx100\fscy100)"
    elif animation == "fade":
        extra = r"\fad(90,70)"
    return rf"{{\c{color}{extra}}}{rendered}{{\c{_ass_color(preset.primary)}\fscx100\fscy100\frz0}}"


def write_ass(
    output_path: Path,
    words: list[Any],
    clip_start: float,
    clip_end: float,
    hook_title: str | None,
    width: int = 1080,
    height: int = 1920,
    style: Any | None = None,
    timeline: list[Any] | None = None,
    hook_preset: str = "bold",
) -> Path:
    preset = _resolved_preset(style)
    mapped = _mapped_words(words, clip_start, clip_end, timeline)
    clip_duration = sum(
        max(0.0, float(_value(item, "end", clip_end)) - float(_value(item, "start", clip_start)))
        for item in (timeline or [{"start": clip_start, "end": clip_end}])
    )
    alignment_name = str(_style_value(style, "alignment", "center") or "center")
    alignment = {"left": 1, "center": 2, "right": 3}.get(alignment_name, 2)
    position = int(_style_value(style, "position", 76) or 76)
    safe_zone = str(_style_value(style, "safe_zone", None) or _style_value(style, "safeZone", "shorts") or "shorts")
    safe_minimum = {"shorts": 300, "reels": 330, "tiktok": 360}.get(safe_zone, 300)
    configured_margin = _style_value(style, "margin_bottom", None) or _style_value(style, "marginBottom", None)
    margin_v = int(configured_margin or max(safe_minimum, height - height * position / 100))
    maximum_words = int(_style_value(style, "max_words", None) or _style_value(style, "maxWords", 5) or 5)
    maximum_lines = int(_style_value(style, "max_lines", None) or _style_value(style, "maxLines", 2) or 2)
    semantic_value = _style_value(style, "semantic_highlight", None)
    semantic = bool(_style_value(style, "semanticHighlight", True) if semantic_value is None else semantic_value)
    background_opacity_value = _style_value(style, "background_opacity", None)
    if background_opacity_value is None:
        background_opacity_value = _style_value(style, "backgroundOpacity", 55)
    background_opacity = int(55 if background_opacity_value is None else background_opacity_value)
    background_alpha = round(255 * (1 - background_opacity / 100))
    border_style = 3 if preset.background else 1

    hook_border = 3 if hook_preset == "boxed" else 1
    hook_size = 58 if hook_preset == "bold" else 50
    horizontal_margin = max(64, int(round(width * 0.10)))
    caption_units_per_line = max(10.0, (width - 2 * horizontal_margin) / max(1.0, preset.size * 0.62 + preset.spacing))
    hook_units_per_line = max(12.0, (width - 2 * horizontal_margin) / max(1.0, hook_size * 0.62 + 1.0))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{preset.font},{preset.size},{_ass_color(preset.primary)},{_ass_color(preset.highlight)},{_ass_color(preset.outline)},{_ass_color("#06101B", background_alpha)},{preset.bold},0,0,0,100,100,{preset.spacing},0,{border_style},{preset.outline_width},{preset.shadow},{alignment},{horizontal_margin},{horizontal_margin},{margin_v},1
Style: Hook,Arial,{hook_size},&H00FFFFFF,&H00FFFFFF,&H00101822,&H90040C15,-1,0,0,0,100,100,1,0,{hook_border},7,2,8,{horizontal_margin},{horizontal_margin},145,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    hook_end = 0.0
    if hook_title:
        hook_end = min(4.2, clip_duration)
        hook_animation = r"{\fad(120,220)\fscx104\fscy104\t(0,180,\fscx100\fscy100)}"
        wrapped_hook = _compact_wrapped_text(hook_title.upper(), 2, hook_units_per_line)
        events.append(
            f"Dialogue: 1,{_ass_time(0.12)},{_ass_time(hook_end)},Hook,,0,0,0,,{hook_animation}{_escape(wrapped_hook)}"
        )

    if preset.key != "none":
        # O hook tem prioridade visual. Enquanto ele estiver na tela, as legendas
        # normais ficam ocultas para evitar texto duplicado no inicio do corte.
        # Palavras que atravessam o fim do hook entram somente a partir desse ponto.
        caption_words = mapped
        if hook_end > 0:
            caption_words = []
            for word in mapped:
                word_end = float(_value(word, "end", 0))
                if word_end <= hook_end:
                    continue
                adjusted = dict(word)
                adjusted["start"] = max(hook_end, float(_value(word, "start", 0)))
                if float(adjusted["end"]) <= float(adjusted["start"]):
                    adjusted["end"] = float(adjusted["start"]) + 0.08
                caption_words.append(adjusted)

        caption_groups = _caption_groups_for_width(caption_words, maximum_words, maximum_lines, caption_units_per_line)
        for group_index, group in enumerate(caption_groups):
            group_texts = [str(_value(word, "word", "")) for word in group]
            line_indexes = _balanced_lines(group_texts, maximum_lines, caption_units_per_line)
            next_group_start = (
                float(_value(caption_groups[group_index + 1][0], "start", clip_duration))
                if group_index + 1 < len(caption_groups) else None
            )
            for index, current in enumerate(group):
                start = max(0.0, float(_value(current, "start", 0)))
                if index + 1 < len(group):
                    end = max(start + 0.08, float(_value(group[index + 1], "start", 0)))
                else:
                    end = min(clip_duration, max(start + 0.16, float(_value(current, "end", 0)) + 0.12))
                    if next_group_start is not None:
                        end = max(start + 0.08, min(end, next_group_start))
                rendered = [
                    _active_word(str(_value(word, "word", "")), preset, semantic, word_index == index)
                    for word_index, word in enumerate(group)
                ]
                rendered_lines = [" ".join(rendered[word_index] for word_index in line) for line in line_indexes]
                rendered_text = r"\N".join(rendered_lines)
                fade = r"{\fad(55,65)}" if preset.animation in {"pop", "glitch"} else ""
                events.append(
                    f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,{fade}{rendered_text}"
                )

    output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return output_path
