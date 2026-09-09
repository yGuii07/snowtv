from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CaptionOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    preset: Literal[
        "none", "karaoke", "bold", "minimal", "podcast", "highlight",
        "bounce", "pop", "deep", "glitch",
    ] = "karaoke"
    font: str = Field(default="Arial", max_length=80)
    size: int | None = Field(default=None, ge=28, le=140)
    weight: Literal["normal", "bold", "black"] = "black"
    uppercase: bool | None = None
    alignment: Literal["left", "center", "right"] = "center"
    position: int = Field(default=76, ge=12, le=88)
    margin_bottom: int | None = Field(default=None, alias="marginBottom", ge=80, le=720)
    max_words: int = Field(default=5, alias="maxWords", ge=1, le=10)
    max_lines: int = Field(default=2, alias="maxLines", ge=1, le=3)
    primary_color: str | None = Field(default=None, alias="primaryColor", pattern=r"^#[0-9A-Fa-f]{6}$")
    highlight_color: str | None = Field(default=None, alias="highlightColor", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_color: str | None = Field(default=None, alias="outlineColor", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline: int | None = Field(default=None, ge=0, le=14)
    shadow: int | None = Field(default=None, ge=0, le=12)
    background: bool | None = None
    background_opacity: int = Field(default=55, alias="backgroundOpacity", ge=0, le=100)
    spacing: float = Field(default=0.0, ge=-2, le=12)
    animation: Literal["none", "karaoke", "bounce", "pop", "glitch", "scale", "fade"] | None = None
    semantic_highlight: bool = Field(default=True, alias="semanticHighlight")
    safe_zone: Literal["shorts", "reels", "tiktok"] = Field(default="shorts", alias="safeZone")


class AdvancedOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    whisper_model: Literal["auto", "tiny", "base", "small", "medium"] = Field(default="auto", alias="whisperModel")
    compute_type: Literal["auto", "int8", "int8_float16", "float16", "float32"] = Field(default="auto", alias="computeType")
    cpu_threads: int = Field(default=0, alias="cpuThreads", ge=0, le=32)
    analysis_width: int = Field(default=0, alias="analysisWidth", ge=0, le=960)
    face_redetect_seconds: float = Field(default=0, alias="faceRedetectSeconds", ge=0, le=5)
    encoder: Literal["auto", "cpu", "amd"] = "auto"
    crf: int = Field(default=0, ge=0, le=35)
    ffmpeg_preset: Literal["auto", "ultrafast", "veryfast", "faster", "fast", "medium", "slow"] = Field(default="auto", alias="ffmpegPreset")


class ClipOverride(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    index: int = Field(ge=1, le=99)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    title: str | None = Field(default=None, max_length=100)


class ProcessOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    language: str = Field(default="pt", max_length=12)
    duration: Literal["auto", "short", "medium", "long", "15_30", "30_45", "30_60", "45_90"] = "auto"
    clip_count: int = Field(default=5, alias="clipCount", ge=1, le=12)
    layout: Literal["auto", "track", "center", "blur", "split", "horizontal"] = "auto"
    performance_profile: Literal["auto", "eco", "balanced", "quality"] = Field(default="auto", alias="performanceProfile")
    editorial_style: Literal["auto", "viral", "educational", "podcast", "storytelling", "commentary"] = Field(default="auto", alias="editorialStyle")
    captions: bool = True
    remove_pauses: bool = Field(default=True, alias="removePauses")
    pause_removal: Literal["off", "light", "normal", "aggressive"] = Field(default="normal", alias="pauseRemoval")
    hook_text: bool = Field(default=True, alias="hookText")
    hook_mode: Literal["off", "auto", "custom"] = Field(default="auto", alias="hookMode")
    hook_title: str = Field(default="", alias="hookTitle", max_length=100)
    hook_preset: Literal["clean", "bold", "boxed"] = Field(default="bold", alias="hookPreset")
    caption_style: CaptionOptions = Field(default_factory=CaptionOptions, alias="captionStyle")
    clip_overrides: list[ClipOverride] = Field(default_factory=list, alias="clipOverrides", max_length=12)
    advanced: AdvancedOptions = Field(default_factory=AdvancedOptions)


class ProcessRequest(ProcessOptions):
    url: HttpUrl
    acknowledged: bool = True


class JobCreated(BaseModel):
    job_id: str
    status: str = "queued"
    progress: int = 0


class ClipFeedbackRequest(BaseModel):
    clip_index: int = Field(ge=1, le=99, alias="clipIndex")
    rating: Literal["good", "bad"]
    reasons: list[Literal[
        "weak_hook", "starts_late", "starts_early", "ends_early", "ends_late",
        "missing_context", "boring", "bad_framing", "bad_captions", "other",
    ]] = Field(default_factory=list, max_length=6)



class HealthResponse(BaseModel):
    status: str
    ffmpeg: bool
    ffprobe: bool
    transcription: str
    selection: str
    face_tracking: str
    queue_workers: int
    hardware: dict[str, Any] = Field(default_factory=dict)
    dependencies: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    encoders: list[str] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)
