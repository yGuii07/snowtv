from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from .editing import EditRange
from .hardware import PerformancePreset, resolve_profile
from .tracking import TrackPoint, crop_x_expression


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class YtDlpAttempt:
    name: str
    format_selector: str | None = None
    player_clients: str = ""


def run_command(command: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as error:
        raise MediaError(f"Dependência não encontrada: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()[-3500:]
        raise MediaError(f"{command[0]} falhou: {detail}") from error


def probe(path: Path) -> dict[str, Any]:
    result = run_command(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        timeout=60,
    )
    payload = json.loads(result.stdout)
    video_stream = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), None)
    if video_stream is None:
        raise MediaError("O arquivo não contém uma faixa de vídeo válida.")
    duration = float(payload.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    return {
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/1",
        "codec": video_stream.get("codec_name") or "unknown",
        "has_audio": any(stream.get("codec_type") == "audio" for stream in payload.get("streams", [])),
    }


def _javascript_runtime_args(settings: Any, log: Callable[[str], None]) -> tuple[list[str], bool]:
    configured = str(getattr(settings, "ytdlp_js_runtime", "auto") or "auto").strip().lower()
    configured_path = str(getattr(settings, "ytdlp_js_runtime_path", "") or "").strip()
    if configured in {"off", "none", "disabled"}:
        log("Runtime JavaScript do yt-dlp desativado por configuração.")
        return [], False

    runtime = "deno" if configured in {"", "auto"} else configured
    runtime_path = configured_path or shutil.which(runtime) or ""
    if not runtime_path:
        log(
            "Deno não foi encontrado no PATH. O yt-dlp continuará com formatos compatíveis, "
            "mas alguns vídeos do YouTube podem exigir um runtime JavaScript."
        )
        return [], False

    runtime_spec = f"{runtime}:{runtime_path}"
    arguments = ["--js-runtimes", runtime_spec]
    if bool(getattr(settings, "ytdlp_remote_components", False)):
        arguments.extend(["--remote-components", "ejs:github"])
    log(f"Runtime JavaScript do yt-dlp: {runtime}.")
    return arguments, True


def _build_ytdlp_command(
    url: str,
    job_dir: Path,
    settings: Any,
    attempt: YtDlpAttempt,
    runtime_args: list[str],
) -> list[str]:
    output_template = str(job_dir / "source.%(ext)s")
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--output",
        output_template,
    ]

    # A strategy without a format selector is intentionally the native yt-dlp
    # path. Keep it as close as possible to `python -m yt_dlp URL -o ...`: no
    # forced format, container, player client, JavaScript runtime or retries.
    # This matters because yt-dlp's own defaults can select a working YouTube
    # format/client combination that an explicit selector would bypass.
    if attempt.format_selector:
        command.extend(
            [
                "--no-progress",
                "--newline",
                "--force-overwrites",
                "--socket-timeout",
                "30",
                "--retries",
                "3",
                "--fragment-retries",
                "3",
                "--restrict-filenames",
                "--format",
                attempt.format_selector,
                *runtime_args,
            ]
        )
        if attempt.player_clients:
            command.extend(["--extractor-args", f"youtube:player_client={attempt.player_clients}"])

    cookies_file = str(getattr(settings, "ytdlp_cookies_file", "") or "").strip()
    if cookies_file:
        command.extend(["--cookies", cookies_file])
    command.append(url)
    return command


def _sanitized_ytdlp_command(command: list[str]) -> str:
    """Return a copy/paste-friendly command without exposing cookie paths."""
    sanitized: list[str] = []
    redact_next = False
    for argument in command:
        if redact_next:
            sanitized.append("[COOKIES_FILE]")
            redact_next = False
            continue
        sanitized.append(argument)
        if argument in {"--cookies", "--cookies-from-browser"}:
            redact_next = True
    if os.name == "nt":
        return subprocess.list2cmdline(sanitized)
    return shlex.join(sanitized)


def _cleanup_ytdlp_outputs(job_dir: Path) -> None:
    for path in job_dir.glob("source.*"):
        if path.is_file():
            path.unlink(missing_ok=True)


def _downloaded_video(job_dir: Path) -> Path | None:
    video_extensions = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}
    files = [
        path
        for path in job_dir.glob("source.*")
        if path.is_file() and path.suffix.lower() in video_extensions
    ]
    return max(files, key=lambda path: path.stat().st_size) if files else None


def _safe_ytdlp_error(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    detail = "\n".join(lines[-24:])
    detail = re.sub(r"https?://\S+", "[URL]", detail)
    return detail[-2400:] or "yt-dlp terminou sem informar o motivo."


def download_youtube(
    url: str,
    job_dir: Path,
    settings: Any,
    log: Callable[[str], None],
    debug_log: Callable[[str], None] | None = None,
) -> Path:
    attempts = [
        YtDlpAttempt("standalone nativo"),
        YtDlpAttempt(
            "seleção controlada de vídeo + áudio",
            str(getattr(settings, "ytdlp_format", "bv*+ba/b") or "bv*+ba/b"),
        ),
        YtDlpAttempt(
            "formato progressivo + cliente alternativo",
            str(
                getattr(
                    settings,
                    "ytdlp_fallback_format",
                    "b[height<=1080][ext=mp4]/b[height<=1080]/b/bv*+ba",
                )
                or "b[height<=1080][ext=mp4]/b[height<=1080]/b/bv*+ba"
            ),
            str(getattr(settings, "ytdlp_fallback_player_clients", "default,-web_safari") or ""),
        ),
    ]
    failures: list[str] = []
    runtime_args: list[str] = []
    has_runtime: bool | None = None
    for index, attempt in enumerate(attempts, start=1):
        if attempt.format_selector and has_runtime is None:
            runtime_args, has_runtime = _javascript_runtime_args(settings, log)

        _cleanup_ytdlp_outputs(job_dir)
        log(f"yt-dlp: tentativa {index}/{len(attempts)} — {attempt.name}.")
        command = _build_ytdlp_command(url, job_dir, settings, attempt, runtime_args)
        command_log = (
            f"yt-dlp tentativa {index}/{len(attempts)} ({attempt.name}) — comando sanitizado: "
            f"{_sanitized_ytdlp_command(command)}"
        )
        if debug_log is None:
            log(f"DEBUG — {command_log}")
        else:
            debug_log(command_log)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        missing_runtime_warning = "no supported javascript runtime could be found" in combined_output.lower()
        if missing_runtime_warning and has_runtime is not True:
            log(
                "Aviso do yt-dlp: nenhum runtime JavaScript foi encontrado. "
                "O modo nativo continuará com os formatos disponíveis; Deno é opcional e será usado nos fallbacks se configurado."
            )

        downloaded = _downloaded_video(job_dir) if completed.returncode == 0 else None
        if downloaded is not None:
            log(f"yt-dlp concluiu download e merge local na tentativa {index} ({downloaded.suffix.lower()}).")
            return downloaded

        detail = _safe_ytdlp_error(combined_output)
        failures.append(f"Tentativa {index} ({attempt.name}): {detail}")
        if index == 1:
            log("A estratégia standalone nativa falhou; tentando seleção controlada de vídeo e áudio.")
        elif index == 2:
            log("A seleção controlada falhou; tentando formato progressivo e cliente alternativo.")

    _cleanup_ytdlp_outputs(job_dir)
    runtime_hint = "" if has_runtime else " Deno não foi detectado; ele é opcional, mas amplia o suporte do YouTube."
    raise MediaError(
        "O yt-dlp falhou após três estratégias de download local."
        f"{runtime_hint}\n" + "\n".join(failures)
    )


def extract_audio(source: Path, output: Path) -> Path:
    run_command(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", str(output),
        ]
    )
    return output


def create_analysis_proxy(source: Path, output: Path, width: int, fps: int = 12) -> Path:
    if output.is_file() and output.stat().st_size > 0:
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.mp4")
    temporary.unlink(missing_ok=True)
    run_command(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-an",
            "-vf", f"scale='min({max(320, width)},iw)':-2:flags=fast_bilinear,fps={max(6, fps)}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
        ]
    )
    os.replace(temporary, output)
    return output


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _encoding_args(profile: PerformancePreset) -> list[str]:
    encoder = str(profile.encoder)
    if "nvenc" in encoder:
        return ["-c:v", encoder, "-preset", "p5", "-cq", str(profile.crf), "-b:v", "0"]
    if encoder == "h264_amf":
        quality = max(16, min(30, int(profile.crf) + 2))
        return [
            "-c:v", encoder, "-quality", "balanced", "-rc", "cqp",
            "-qp_i", str(quality), "-qp_p", str(quality), "-qp_b", str(quality + 2),
        ]
    if "videotoolbox" in encoder:
        return ["-c:v", encoder, "-q:v", str(max(40, min(90, 100 - profile.crf * 2)))]
    return [
        "-c:v", encoder, "-preset", str(profile.ffmpeg_preset), "-crf", str(profile.crf),
        "-threads", str(profile.ffmpeg_threads),
    ]


def render_clip(
    source: Path,
    output: Path,
    ass_path: Path | None,
    start: float,
    end: float,
    layout: str,
    metadata: dict[str, Any],
    track_points: list[TrackPoint],
    settings: Any,
    profile: PerformancePreset | None = None,
    timeline: list[EditRange] | None = None,
    split_centers: tuple[float, float] | None = None,
    log: Callable[[str], None] | None = None,
) -> Path:
    profile = profile or resolve_profile(settings, "auto")
    ranges = timeline or [EditRange(start, end)]
    ranges = [item for item in ranges if item.end - item.start >= 0.08] or [EditRange(start, end)]
    input_start = ranges[0].start
    input_end = ranges[-1].end
    duration = max(0.2, sum(item.end - item.start for item in ranges))
    source_width = int(metadata["width"])
    source_height = int(metadata["height"])
    out_width = int(profile.output_width)
    out_height = int(profile.output_height)
    target_ratio = out_width / out_height
    source_ratio = source_width / max(1, source_height)

    final_label = "framed"
    if layout == "horizontal":
        base = (
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[{final_label}]"
        )
    elif layout == "split" and source_width > source_height:
        panel_width = max(2, int(source_height * (out_width / (out_height / 2))) // 2 * 2)
        maximum_panel_x = max(0, source_width - panel_width)
        if split_centers:
            left_x = max(0, min(maximum_panel_x, int(split_centers[0] - panel_width / 2)))
            right_x = max(0, min(maximum_panel_x, int(split_centers[1] - panel_width / 2)))
        else:
            left_x = 0
            right_x = maximum_panel_x
        base = (
            "[0:v]split=2[split_left][split_right];"
            f"[split_left]crop={panel_width}:{source_height}:{left_x}:0,scale={out_width}:{out_height // 2}:force_original_aspect_ratio=increase,crop={out_width}:{out_height // 2}[top];"
            f"[split_right]crop={panel_width}:{source_height}:{right_x}:0,scale={out_width}:{out_height // 2}:force_original_aspect_ratio=increase,crop={out_width}:{out_height // 2}[bottom];"
            f"[top][bottom]vstack=inputs=2,setsar=1[{final_label}]"
        )
    elif layout == "blur" or source_ratio <= target_ratio:
        base = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={out_width}:{out_height}:force_original_aspect_ratio=increase,"
            f"crop={out_width}:{out_height},boxblur=28:10[blur];"
            f"[fg]scale={out_width}:{out_height}:force_original_aspect_ratio=decrease[front];"
            f"[blur][front]overlay=(W-w)/2:(H-h)/2,setsar=1[{final_label}]"
        )
    else:
        crop_width = max(2, int(source_height * target_ratio) // 2 * 2)
        if layout in {"track", "auto"}:
            x_expression = crop_x_expression(track_points, source_width, crop_width)
        else:
            x_expression = f"{max(0, source_width - crop_width) / 2:.3f}"
        base = (
            f"[0:v]crop=w={crop_width}:h={source_height}:x='{x_expression}':y=0,"
            f"scale={out_width}:{out_height}:flags=lanczos,setsar=1[{final_label}]"
        )

    graph_parts = [base]
    audio_map = "0:a?"
    audio_filter_args = ["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"]
    video_source_label = final_label
    if len(ranges) > 1:
        count = len(ranges)
        video_inputs = "".join(f"[vsrc{index}]" for index in range(count))
        audio_inputs = "".join(f"[asrc{index}]" for index in range(count))
        graph_parts.append(f"[{final_label}]split={count}{video_inputs}")
        graph_parts.append(f"[0:a]asplit={count}{audio_inputs}")
        concat_inputs = []
        for index, item in enumerate(ranges):
            relative_start = max(0.0, item.start - input_start)
            relative_end = max(relative_start + 0.08, item.end - input_start)
            graph_parts.append(
                f"[vsrc{index}]trim=start={relative_start:.3f}:end={relative_end:.3f},setpts=PTS-STARTPTS[v{index}]"
            )
            graph_parts.append(
                f"[asrc{index}]atrim=start={relative_start:.3f}:end={relative_end:.3f},asetpts=PTS-STARTPTS[a{index}]"
            )
            concat_inputs.extend([f"[v{index}]", f"[a{index}]"])
        graph_parts.append(f"{''.join(concat_inputs)}concat=n={count}:v=1:a=1[joined][aout]")
        graph_parts.append("[aout]loudnorm=I=-16:LRA=11:TP=-1.5[afinal]")
        video_source_label = "joined"
        audio_map = "[afinal]"
        audio_filter_args = []

    if ass_path and ass_path.exists():
        graph_parts.append(f"[{video_source_label}]subtitles=filename='{_filter_path(ass_path)}'[vout]")
    else:
        graph_parts.append(f"[{video_source_label}]null[vout]")
    graph = ";".join(graph_parts)

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{input_start:.3f}", "-i", str(source), "-t", f"{max(0.2, input_end - input_start):.3f}",
        "-filter_complex", graph, "-map", "[vout]", "-map", audio_map,
        "-r", str(profile.output_fps), *_encoding_args(profile),
        "-c:a", "aac", "-b:a", "160k", *audio_filter_args,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-max_muxing_queue_size", "2048", str(output),
    ]
    try:
        run_command(command)
    except MediaError:
        if profile.encoder == "libx264":
            raise
        if log:
            log(f"O encoder {profile.encoder} falhou; repetindo automaticamente com libx264.")
        output.unlink(missing_ok=True)
        fallback = replace(profile, encoder="libx264")
        fallback_command = command[:]
        encoder_index = fallback_command.index("-c:v")
        audio_index = fallback_command.index("-c:a")
        fallback_command[encoder_index:audio_index] = _encoding_args(fallback)
        run_command(fallback_command)
    return output


def dependencies_available() -> tuple[bool, bool]:
    return shutil.which("ffmpeg") is not None, shutil.which("ffprobe") is not None
