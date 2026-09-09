from __future__ import annotations

import gc
import json
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .cache import CacheManager
from .captions import write_ass
from .editing import EditRange, build_edit_timeline, timeline_duration
from .hardware import PerformancePreset, resolve_profile
from .media import create_analysis_proxy, download_youtube, extract_audio, probe, render_clip
from .models import ProcessOptions
from .selector import Highlight, HighlightSelector, highlight_as_dict
from .store import JobStore
from .tracking import FaceTrackResult, TrackPoint, analyze_face_track
from .transcription import Transcript, Transcriber


class JobCancelled(RuntimeError):
    pass


class Pipeline:
    def __init__(
        self,
        settings: Any,
        store: JobStore,
        transcriber: Transcriber,
        selector: HighlightSelector,
    ):
        self.settings = settings
        self.store = store
        self.transcriber = transcriber
        self.selector = selector
        self.cache = CacheManager(settings.resolved_cache_dir, bool(settings.cache_enabled))

    def _stage(self, job_id: str, progress: int, stage: str, message: str) -> None:
        self._check_cancelled(job_id)
        self.store.update(job_id, status="processing", progress=max(0, min(99, progress)), stage=stage, error=None)
        self.store.append_log(job_id, message)

    def _check_cancelled(self, job_id: str) -> None:
        if self.store.get(job_id).get("cancel_requested"):
            raise JobCancelled("Processamento cancelado pelo usuário.")

    @staticmethod
    def _tracking_payload(value: FaceTrackResult | list[TrackPoint]) -> dict[str, Any]:
        if isinstance(value, FaceTrackResult):
            return {
                "kind": "analysis",
                "points": [{"time": item.time, "center_x": item.center_x} for item in value.points],
                "detection_samples": value.detection_samples,
                "face_samples": value.face_samples,
                "two_face_samples": value.two_face_samples,
                "split_centers": list(value.split_centers) if value.split_centers else None,
                "scene_resets": value.scene_resets,
            }
        return {"kind": "points", "points": [{"time": item.time, "center_x": item.center_x} for item in value]}

    @staticmethod
    def _tracking_from_payload(value: dict[str, Any]) -> FaceTrackResult | list[TrackPoint]:
        points = [
            TrackPoint(float(item["time"]), float(item["center_x"]))
            for item in value.get("points", [])
            if isinstance(item, dict) and "time" in item and "center_x" in item
        ]
        if value.get("kind") != "analysis":
            return points
        centers = value.get("split_centers")
        split_centers = (
            (float(centers[0]), float(centers[1]))
            if isinstance(centers, list) and len(centers) == 2 else None
        )
        return FaceTrackResult(
            points,
            int(value.get("detection_samples") or 0),
            int(value.get("face_samples") or 0),
            int(value.get("two_face_samples") or 0),
            split_centers,
            int(value.get("scene_resets") or 0),
        )

    @staticmethod
    def _timed(timings: dict[str, float], name: str, operation: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        try:
            return operation()
        finally:
            timings[name] = round(timings.get(name, 0.0) + time.perf_counter() - started, 3)

    @staticmethod
    def _highlight_from_dict(value: dict[str, Any]) -> Highlight:
        return Highlight(
            candidate_id=int(value.get("candidate_id") or 0),
            start=float(value.get("start") or 0),
            end=float(value.get("end") or 0),
            text=str(value.get("text") or ""),
            title=str(value.get("title") or "Momento em destaque"),
            score=int(value.get("score") or 1),
            reason=str(value.get("reason") or "Trecho claro e independente."),
            selection_method=str(value.get("selection_method") or "heuristic"),
            score_breakdown=dict(value.get("score_breakdown") or {}),
        )

    @staticmethod
    def _friendly_error(error: Exception) -> str:
        message = str(error).strip()
        lowered = message.lower()
        if "yt-dlp" in lowered or "http error 403" in lowered or "youtube" in lowered:
            return "Não foi possível importar esse vídeo do YouTube após três tentativas. Veja os detalhes técnicos e confirme o link e o yt-dlp; Deno é opcional."
        if "ffmpeg" in lowered or "ffprobe" in lowered:
            return "O FFmpeg não conseguiu preparar ou renderizar o vídeo. Confirme a instalação e tente novamente."
        if "memory" in lowered or "memória" in lowered or "bad allocation" in lowered:
            return "O computador ficou sem memória disponível. Feche programas pesados ou use o perfil Eco."
        if "transcri" in lowered or "whisper" in lowered:
            return "A transcrição local não pôde ser concluída. Tente o perfil Eco ou um modelo Whisper menor."
        if message:
            return message[:700]
        return "O Snow Engine encontrou uma falha inesperada durante o processamento."

    def _resolve_source(
        self,
        job: dict[str, Any],
        job_dir: Path,
        job_id: str,
        timings: dict[str, float],
    ) -> tuple[Path, str, bool]:
        cache_hit = False
        if job["source_kind"] == "url":
            self._stage(job_id, 3, "downloading", "Procurando o vídeo no cache local.")
            cached = self.cache.source_for_url(job["source_ref"])
            if cached is not None:
                source = self._timed(timings, "download", lambda: self.cache.materialize_source(cached, job_dir))
                content_hash = cached.content_hash
                cache_hit = True
                self.store.append_log(job_id, "Vídeo reutilizado do cache; nenhum novo download foi necessário.")
            else:
                self._stage(job_id, 4, "downloading", "Importando e mesclando o vídeo com o yt-dlp.")
                source = self._timed(
                    timings,
                    "download",
                    lambda: download_youtube(
                        job["source_ref"],
                        job_dir,
                        self.settings,
                        lambda message: self.store.append_log(job_id, message),
                        lambda detail: self.store.append_log(
                            job_id,
                            "Comando yt-dlp sanitizado registrado para reprodução manual.",
                            detail=detail,
                            level="debug",
                        ),
                    ),
                )
                cached = self._timed(
                    timings,
                    "source_hash",
                    lambda: self.cache.register_source(source, job["source_ref"], "url"),
                )
                content_hash = cached.content_hash
            self.store.update(job_id, source_path=str(source))
            return source, content_hash, cache_hit

        self._stage(job_id, 3, "importing", "Validando o arquivo de origem local.")
        source = Path(str(job["source_path"] or ""))
        if not source.exists():
            raise RuntimeError("O arquivo original não está mais disponível no armazenamento local.")
        inherited_hash = str(job.get("options", {}).get("_sourceHash") or "")
        if job["source_kind"] == "reuse" and len(inherited_hash) == 64:
            self.store.append_log(job_id, "Hash da fonte herdado do projeto original; leitura completa do vídeo dispensada.")
            return source, inherited_hash, True
        cached = self._timed(
            timings,
            "source_hash",
            lambda: self.cache.register_source(source, job["source_ref"], job["source_kind"]),
        )
        return source, cached.content_hash, cache_hit

    def _load_metadata(self, source: Path, content_hash: str, timings: dict[str, float]) -> tuple[dict[str, Any], bool]:
        path = self.cache.metadata_path(content_hash)
        cached = self.cache.load_json(path)
        if isinstance(cached, dict) and int(cached.get("width") or 0) > 0:
            return cached, True
        metadata = self._timed(timings, "probe", lambda: probe(source))
        self.cache.save_json(path, metadata)
        return metadata, False

    def _load_transcript(
        self,
        source: Path,
        content_hash: str,
        language: str,
        profile: PerformancePreset,
        job_id: str,
        job_dir: Path,
        timings: dict[str, float],
    ) -> tuple[Transcript, bool]:
        cache_path = self.cache.transcript_path(content_hash, language, profile.whisper_model)
        cached = self.cache.load_json(cache_path)
        if isinstance(cached, dict) and cached.get("words"):
            self._stage(job_id, 43, "transcribing", "Transcrição encontrada no cache; o Whisper não será executado novamente.")
            return Transcript.from_dict(cached), True

        self._stage(job_id, 12, "extracting_audio", "Extraindo áudio mono de 16 kHz com FFmpeg.")
        audio_path = self._timed(timings, "audio", lambda: extract_audio(source, job_dir / "audio.wav"))
        self._stage(
            job_id,
            20,
            "transcribing",
            f"Transcrevendo localmente com faster-whisper {profile.whisper_model} ({profile.compute_type}, {profile.cpu_threads} threads).",
        )
        last_progress = -1

        def report(fraction: float) -> None:
            nonlocal last_progress
            self._check_cancelled(job_id)
            progress = 20 + int(max(0.0, min(1.0, fraction)) * 23)
            if progress >= last_progress + 2:
                last_progress = progress
                self.store.update(job_id, status="processing", progress=progress, stage="transcribing")

        transcript = self._timed(
            timings,
            "transcription",
            lambda: self.transcriber.transcribe(audio_path, language, profile, report),
        )
        self.cache.save_json(cache_path, transcript.as_dict())
        audio_path.unlink(missing_ok=True)
        return transcript, False

    def _load_highlights(
        self,
        transcript: Transcript,
        content_hash: str,
        options: ProcessOptions,
        job_id: str,
        timings: dict[str, float],
    ) -> tuple[list[Highlight], bool]:
        selection_options = {
            "duration": options.duration,
            "count": options.clip_count,
            "language": transcript.language,
            "provider": str(self.settings.llm_provider),
            "model": str(self.settings.llm_model),
            "selector_version": 5,
            "editorial_style": options.editorial_style,
        }
        path = self.cache.selection_path(content_hash, selection_options)
        cached = self.cache.load_json(path)
        if isinstance(cached, list) and cached:
            self._stage(job_id, 52, "selecting", "Análise editorial reutilizada do cache local.")
            return [self._highlight_from_dict(item) for item in cached if isinstance(item, dict)], True
        self._stage(job_id, 48, "analyzing", f"Editorial Engine 2.0: analisando boundaries, hook, contexto, conclusão e diversidade ({options.editorial_style}).")
        highlights = self._timed(
            timings,
            "selection",
            lambda: self.selector.select(transcript.words, str(options.duration), options.clip_count, transcript.language, options.editorial_style),
        )
        candidate_count = int(getattr(self.selector, "last_stats", {}).get("candidate_count", 0) or 0)
        self._stage(job_id, 53, "selecting", f"Ranking concluído; {len(highlights)} momentos selecionados entre {candidate_count or 'vários'} candidatos.")
        self.cache.save_json(path, [highlight_as_dict(item) for item in highlights])
        return highlights, False

    def process(self, job_id: str) -> None:
        job_dir = self.settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        total_started = time.perf_counter()
        timings: dict[str, float] = {}
        try:
            job = self.store.get(job_id)
            options = ProcessOptions.model_validate(job["options"])
            profile = resolve_profile(self.settings, options.performance_profile, options.advanced)
            self.store.append_log(
                job_id,
                f"Perfil {profile.name.title()}: {profile.whisper_model}/CPU {profile.compute_type}, "
                f"{profile.cpu_threads} threads, encoder {profile.encoder}.",
            )
            if options.advanced.encoder == "amd" and profile.encoder != "h264_amf":
                self.store.append_log(
                    job_id,
                    "Encoder AMD não está disponível neste FFmpeg; usando libx264 automaticamente.",
                    level="warning",
                )

            source, content_hash, source_cache_hit = self._resolve_source(job, job_dir, job_id, timings)
            self._stage(job_id, 8, "analyzing", "Lendo metadados e validando duração, vídeo e áudio.")
            metadata, metadata_cache_hit = self._load_metadata(source, content_hash, timings)
            if metadata["duration"] <= 0:
                raise RuntimeError("Não foi possível determinar a duração do vídeo.")
            if metadata["duration"] > self.settings.max_video_minutes * 60:
                raise RuntimeError(f"O vídeo excede o limite configurado de {self.settings.max_video_minutes} minutos.")
            if not metadata.get("has_audio"):
                raise RuntimeError("O vídeo não possui uma faixa de áudio para transcrever.")
            (job_dir / "media.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

            transcript, transcript_cache_hit = self._load_transcript(
                source,
                content_hash,
                options.language,
                profile,
                job_id,
                job_dir,
                timings,
            )
            if len(transcript.words) < 8:
                raise RuntimeError("A transcrição não encontrou fala suficiente para criar cortes.")
            (job_dir / "transcript.json").write_text(
                json.dumps(transcript.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

            highlights, selection_cache_hit = self._load_highlights(
                transcript, content_hash, options, job_id, timings
            )
            if not highlights:
                raise RuntimeError("Não foi possível formar cortes completos com a duração selecionada.")

            # Post-selection editorial overrides are intentionally applied after the
            # cached selection stage. This lets the user trim or retitle a clip and
            # rerender without invalidating the expensive Whisper/editorial caches.
            if options.clip_overrides:
                override_by_index = {item.index: item for item in options.clip_overrides}
                adjusted: list[Highlight] = []
                for clip_index, highlight in enumerate(highlights, start=1):
                    override = override_by_index.get(clip_index)
                    if override is None:
                        adjusted.append(highlight)
                        continue
                    start = highlight.start if override.start is None else max(0.0, min(float(override.start), transcript.duration - 0.4))
                    end = highlight.end if override.end is None else min(transcript.duration, max(float(override.end), start + 0.4))
                    title = (override.title or highlight.title).strip()[:100] or highlight.title
                    adjusted.append(Highlight(
                        candidate_id=highlight.candidate_id, start=start, end=end, text=highlight.text,
                        title=title, score=highlight.score, reason=highlight.reason,
                        selection_method=highlight.selection_method + "+manual", score_breakdown=highlight.score_breakdown,
                    ))
                highlights = adjusted
                self.store.append_log(job_id, f"Aplicados {len(options.clip_overrides)} ajustes editoriais sem repetir a seleção/Whisper.")

            (job_dir / "highlights.json").write_text(
                json.dumps([highlight_as_dict(item) for item in highlights], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            layout = str(options.layout)
            landscape = metadata["width"] / max(1, metadata["height"]) > 9 / 16
            resolved_layout = "track" if layout == "auto" and landscape else "blur" if layout == "auto" else layout
            analysis_source = source
            proxy_cache_hit = False
            if resolved_layout == "track" and landscape:
                proxy_path = (
                    self.cache.proxy_path(content_hash, profile.analysis_width)
                    if self.settings.cache_enabled
                    else job_dir / "analysis-proxy.mp4"
                )
                proxy_cache_hit = proxy_path.is_file() and proxy_path.stat().st_size > 0
                if not proxy_cache_hit:
                    self._stage(job_id, 55, "tracking", f"Criando proxy {profile.analysis_width}p para análise facial eficiente.")
                    self._timed(
                        timings,
                        "proxy",
                        lambda: create_analysis_proxy(source, proxy_path, profile.analysis_width),
                    )
                analysis_source = proxy_path

            clips_dir = job_dir / "clips"
            clips_dir.mkdir(exist_ok=True)
            clips: list[dict[str, Any]] = []
            tracking_cache_hits = 0
            tracking_cache_misses = 0
            raw_options = job["options"]
            pause_mode = str(options.pause_removal)
            if not options.remove_pauses:
                pause_mode = "off"
            elif "pauseRemoval" not in raw_options and "pause_removal" not in raw_options:
                pause_mode = "normal"
            hook_mode = str(options.hook_mode)
            if not options.hook_text:
                hook_mode = "off"

            tracking_settings = SimpleNamespace(
                face_sample_fps=profile.face_sample_fps,
                face_redetect_seconds=(
                    float(options.advanced.face_redetect_seconds)
                    if options.advanced.face_redetect_seconds > 0
                    else profile.face_redetect_seconds
                ),
                analysis_width=profile.analysis_width,
            )

            for index, highlight in enumerate(highlights, start=1):
                self._check_cancelled(job_id)
                timeline = build_edit_timeline(highlight.start, highlight.end, transcript.words, pause_mode)
                base_progress = 57 + int((index - 1) / len(highlights) * 38)
                track_points = []
                clip_layout = resolved_layout
                split_centers: tuple[float, float] | None = None
                if resolved_layout == "track" and landscape:
                    self._stage(
                        job_id,
                        base_progress,
                        "tracking",
                        f"Analisando rosto e suavizando enquadramento do corte {index}/{len(highlights)}.",
                    )
                    tracking_started = time.perf_counter()
                    try:
                        tracking_key = {
                            "version": 2,
                            "ranges": [item.as_dict() for item in timeline],
                            "analysis_width": profile.analysis_width,
                            "sample_fps": profile.face_sample_fps,
                            "redetect": tracking_settings.face_redetect_seconds,
                            "coordinate_width": int(metadata["width"]),
                            "scene_aware": layout == "auto",
                        }
                        tracking_path = self.cache.tracking_path(content_hash, tracking_key)
                        cached_tracking = self.cache.load_json(tracking_path)
                        if isinstance(cached_tracking, dict) and "points" in cached_tracking:
                            track_analysis = self._tracking_from_payload(cached_tracking)
                            tracking_cache_hits += 1
                            self.store.append_log(job_id, f"Corte {index}: tracking reutilizado do cache.")
                        else:
                            track_analysis = analyze_face_track(
                                analysis_source,
                                timeline[0].start,
                                timeline[-1].end,
                                tracking_settings,
                                coordinate_width=float(metadata["width"]),
                                include_scene=layout == "auto",
                            )
                            tracking_cache_misses += 1
                            self.cache.save_json(tracking_path, self._tracking_payload(track_analysis))
                        if isinstance(track_analysis, FaceTrackResult):
                            track_points = track_analysis.points
                            if layout == "auto" and track_analysis.recommended_layout == "split":
                                clip_layout = "split"
                                track_points = []
                                split_centers = track_analysis.split_centers
                                self.store.append_log(
                                    job_id,
                                    f"Corte {index}: duas faces persistentes ({track_analysis.two_face_ratio:.0%} das amostras); usando layout dividido.",
                                )
                        else:
                            track_points = track_analysis
                    except Exception:
                        track_points = []
                        self.store.append_log(
                            job_id,
                            f"Corte {index}: o tracking falhou; o SnowTV continuou com crop central.",
                            detail=traceback.format_exc(),
                            level="warning",
                        )
                    finally:
                        timings["tracking"] = round(
                            timings.get("tracking", 0.0) + time.perf_counter() - tracking_started, 3
                        )
                    if clip_layout != "split":
                        if track_points:
                            self.store.append_log(job_id, f"Corte {index}: enquadramento suavizado com {len(track_points)} pontos.")
                        else:
                            self.store.append_log(job_id, f"Corte {index}: nenhuma face confiável; usando crop central.", level="warning")

                caption_style = options.caption_style
                captions_enabled = options.captions and caption_style.preset != "none"
                hook_title: str | None
                if hook_mode == "off":
                    hook_title = None
                elif hook_mode == "custom" and options.hook_title.strip():
                    hook_title = options.hook_title.strip()
                else:
                    hook_title = highlight.title

                ass_path: Path | None = None
                if captions_enabled or hook_title:
                    ass_path = write_ass(
                        job_dir / f"captions-{index:02d}.ass",
                        transcript.words if captions_enabled else [],
                        highlight.start,
                        highlight.end,
                        hook_title,
                        profile.output_width,
                        profile.output_height,
                        style=caption_style,
                        timeline=timeline,
                        hook_preset=options.hook_preset,
                    )

                self._stage(
                    job_id,
                    min(96, base_progress + 3),
                    "rendering",
                    f"Renderizando corte {index}/{len(highlights)} em {profile.output_width}x{profile.output_height}.",
                )
                output_name = f"clip-{index:02d}.mp4"
                output_path = clips_dir / output_name
                render_started = time.perf_counter()
                render_clip(
                    source=source,
                    output=output_path,
                    ass_path=ass_path,
                    start=highlight.start,
                    end=highlight.end,
                    layout=clip_layout,
                    metadata=metadata,
                    track_points=track_points,
                    settings=self.settings,
                    profile=profile,
                    timeline=timeline,
                    split_centers=split_centers,
                    log=lambda message: self.store.append_log(job_id, message, level="warning"),
                )
                timings["render"] = round(timings.get("render", 0.0) + time.perf_counter() - render_started, 3)
                clips.append(
                    {
                        "id": f"{job_id}-{index}",
                        "title": highlight.title,
                        "video_title_for_youtube_short": highlight.title,
                        "start": round(highlight.start, 3),
                        "end": round(highlight.end, 3),
                        "source_duration": round(highlight.end - highlight.start, 3),
                        "duration": round(timeline_duration(timeline), 3),
                        "edit_timeline": [item.as_dict() for item in timeline],
                        "score": highlight.score,
                        "viral_score": highlight.score,
                        "score_breakdown": highlight.score_breakdown,
                        "reason": highlight.reason,
                        "selection_method": highlight.selection_method,
                        "layout": clip_layout if track_points or clip_layout != "track" else "center",
                        "caption_preset": caption_style.preset if captions_enabled else "none",
                        "video_url": f"/media/{job_id}/{output_name}",
                        "download_url": f"/media/{job_id}/{output_name}?download=1",
                    }
                )

            timings["total"] = round(time.perf_counter() - total_started, 3)
            result = {
                "job_id": job_id,
                "title": highlights[0].title,
                "source_hash": content_hash,
                "source": {
                    "duration": metadata["duration"],
                    "width": metadata["width"],
                    "height": metadata["height"],
                    "codec": metadata["codec"],
                },
                "transcript": {
                    "language": transcript.language,
                    "language_probability": transcript.language_probability,
                    "word_count": len(transcript.words),
                },
                "selection_provider": self.settings.llm_provider,
                "editorial": {"selector_version": 5, "style": options.editorial_style, **dict(getattr(self.selector, "last_stats", {}) or {})},
                "profile": profile.as_dict(),
                "cache": {
                    "source": source_cache_hit,
                    "metadata": metadata_cache_hit,
                    "transcript": transcript_cache_hit,
                    "selection": selection_cache_hit,
                    "analysis_proxy": proxy_cache_hit,
                    "tracking": tracking_cache_hits > 0 and tracking_cache_misses == 0,
                    "tracking_hits": tracking_cache_hits,
                },
                "timings": timings,
                "clips": clips,
            }
            (job_dir / "metrics.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
            self.store.update(job_id, status="completed", progress=100, stage="completed", result=result, error=None)
            self.store.append_log(
                job_id,
                f"Concluído: {len(clips)} cortes em {timings['total']:.1f}s "
                f"(transcrição {timings.get('transcription', 0):.1f}s, render {timings.get('render', 0):.1f}s).",
            )
        except JobCancelled:
            timings["total"] = round(time.perf_counter() - total_started, 3)
            (job_dir / "metrics.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
            current = self.store.get(job_id)
            if current["status"] != "cancelled":
                self.store.update(
                    job_id, status="cancelled", progress=100, stage="cancelled",
                    error="Processamento cancelado pelo usuário.", cancel_requested=1,
                )
            self.store.append_log(job_id, "Processamento interrompido em um ponto seguro.", level="warning")
        except Exception as error:
            timings["total"] = round(time.perf_counter() - total_started, 3)
            if self.store.get(job_id).get("cancel_requested"):
                (job_dir / "metrics.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
                self.store.update(
                    job_id, status="cancelled", progress=100, stage="cancelled",
                    error="Processamento cancelado pelo usuário.", cancel_requested=1,
                )
                self.store.append_log(job_id, "Processamento interrompido após a operação externa atual.", level="warning")
                return
            technical = traceback.format_exc()
            friendly = self._friendly_error(error)
            (job_dir / "error.log").write_text(technical, encoding="utf-8")
            (job_dir / "metrics.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
            self.store.update(job_id, status="failed", progress=100, stage="failed", error=friendly)
            self.store.append_log(job_id, f"Falha: {friendly}", detail=technical, level="error")
        finally:
            gc.collect()
