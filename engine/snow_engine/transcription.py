from __future__ import annotations

import threading
import gc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(slots=True)
class Word:
    start: float
    end: float
    word: str
    probability: float = 1.0


@dataclass(slots=True)
class Transcript:
    language: str
    language_probability: float
    duration: float
    text: str
    words: list[Word]

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "language_probability": self.language_probability,
            "duration": self.duration,
            "text": self.text,
            "words": [asdict(word) for word in self.words],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Transcript":
        return cls(
            language=str(value.get("language") or "unknown"),
            language_probability=float(value.get("language_probability") or 0.0),
            duration=float(value.get("duration") or 0.0),
            text=str(value.get("text") or ""),
            words=[
                Word(
                    start=float(item.get("start") or 0.0),
                    end=float(item.get("end") or item.get("start") or 0.0),
                    word=str(item.get("word") or ""),
                    probability=float(item.get("probability") or 0.0),
                )
                for item in value.get("words", [])
                if isinstance(item, dict) and str(item.get("word") or "").strip()
            ],
        )


class Transcriber:
    def __init__(self, settings: Any):
        self.settings = settings
        self._model: Any = None
        self._model_key: tuple[str, str, str, int] | None = None
        self._model_lock = threading.Lock()

    def _device_and_compute_type(self, profile: Any | None = None) -> tuple[str, str]:
        device = str(self.settings.whisper_device).lower()
        compute_type = str(getattr(profile, "compute_type", self.settings.whisper_compute_type)).lower()
        if device == "auto":
            try:
                import ctranslate2

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        return device, compute_type

    def _get_model(self, profile: Any) -> Any:
        device, compute_type = self._device_and_compute_type(profile)
        model_name = str(getattr(profile, "whisper_model", self.settings.whisper_model))
        cpu_threads = int(getattr(profile, "cpu_threads", self.settings.whisper_cpu_threads) or 0)
        key = (model_name, device, compute_type, cpu_threads)
        if self._model is not None and self._model_key == key:
            return self._model
        with self._model_lock:
            if self._model is None or self._model_key != key:
                from faster_whisper import WhisperModel

                kwargs: dict[str, Any] = {"device": device, "compute_type": compute_type}
                if cpu_threads > 0:
                    kwargs["cpu_threads"] = cpu_threads
                previous = self._model
                self._model = WhisperModel(model_name, **kwargs)
                self._model_key = key
                if previous is not None:
                    del previous
                    gc.collect()
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        language: str = "auto",
        profile: Any | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> Transcript:
        if profile is None:
            from .hardware import resolve_profile

            profile = resolve_profile(self.settings, "auto")
        model = self._get_model(profile)
        segments, info = model.transcribe(
            str(audio_path),
            language=None if language in {"", "auto"} else language,
            beam_size=int(getattr(profile, "beam_size", 4)),
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 450},
            condition_on_previous_text=False,
        )
        words: list[Word] = []
        text_parts: list[str] = []
        for segment in segments:
            segment_text = str(segment.text).strip()
            if segment_text:
                text_parts.append(segment_text)
            segment_words = list(segment.words or [])
            if segment_words:
                for item in segment_words:
                    clean = str(item.word).strip()
                    if clean:
                        words.append(
                            Word(
                                start=max(0.0, float(item.start)),
                                end=max(float(item.start), float(item.end)),
                                word=clean,
                                probability=float(item.probability or 0.0),
                            )
                        )
            elif segment_text:
                tokens = segment_text.split()
                step = max(0.05, (float(segment.end) - float(segment.start)) / max(1, len(tokens)))
                for index, token in enumerate(tokens):
                    start = float(segment.start) + index * step
                    words.append(Word(start=start, end=start + step, word=token, probability=0.5))
            if progress_callback:
                estimated_duration = float(getattr(info, "duration", 0.0) or 0.0)
                progress_callback(min(1.0, float(segment.end) / max(0.001, estimated_duration)))

        duration = float(getattr(info, "duration", words[-1].end if words else 0.0) or 0.0)
        return Transcript(
            language=str(getattr(info, "language", language if language != "auto" else "unknown")),
            language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            duration=duration,
            text=" ".join(text_parts).strip(),
            words=words,
        )
