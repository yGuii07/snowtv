from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PerformancePreset:
    name: str
    whisper_model: str
    compute_type: str
    cpu_threads: int
    ffmpeg_threads: int
    analysis_width: int
    face_sample_fps: float
    face_redetect_seconds: float
    encoder: str
    ffmpeg_preset: str
    crf: int
    output_width: int
    output_height: int
    output_fps: int
    beam_size: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_version(command: list[str], timeout: int = 8) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr or "").strip()
    return output.splitlines()[0][:180] if output else None


def _cpu_name() -> str:
    if os.name == "nt":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell:
            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                detected = result.stdout.strip()
                if detected:
                    return detected
            except (OSError, subprocess.TimeoutExpired):
                pass
    candidates = [
        os.environ.get("PROCESSOR_IDENTIFIER", ""),
        platform.processor(),
        platform.uname().processor,
    ]
    if os.name != "nt":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    candidates.insert(0, line.split(":", 1)[1].strip())
                    break
        except OSError:
            pass
    return next((value.strip() for value in candidates if value and value.strip()), "CPU não identificada")


def _ram_gb() -> float:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return round(status.ullTotalPhys / 1024**3, 1)
        except (AttributeError, OSError):
            pass
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (AttributeError, OSError, ValueError):
        return 0.0


def _gpu_names() -> list[str]:
    commands: list[list[str]] = []
    if os.name == "nt":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell:
            commands.append([
                powershell,
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ' | '",
            ])
    elif shutil.which("lspci"):
        commands.append(["lspci"])
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=4, errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            continue
        lines = [line.strip() for line in result.stdout.split("|") if line.strip()]
        if command[0].endswith("lspci"):
            lines = [line.strip() for line in result.stdout.splitlines() if re.search(r"VGA|3D controller", line, re.I)]
        if lines:
            return lines[:6]
    return []


@lru_cache(maxsize=1)
def ffmpeg_encoders() -> tuple[str, ...]:
    if not shutil.which("ffmpeg"):
        return ()
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    found = set(re.findall(r"^\s*[A-Z\.]{6}\s+([\w-]+)\s", result.stdout, flags=re.MULTILINE))
    return tuple(sorted(found))


@lru_cache(maxsize=1)
def detect_hardware() -> dict[str, Any]:
    logical = max(1, os.cpu_count() or 1)
    cpu = _cpu_name()
    ram = _ram_gb()
    gpus = _gpu_names()
    target = "ryzen 5 4600g" in cpu.lower() and 12 <= ram <= 20
    return {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "cpu": cpu,
        "logical_cores": logical,
        "estimated_physical_cores": max(1, logical // 2) if "AMD" in cpu.upper() or "INTEL" in cpu.upper() else logical,
        "ram_gb": ram,
        "gpu": gpus,
        "target_ryzen_4600g": target,
    }


def _auto_profile_name(hardware: dict[str, Any]) -> str:
    logical = int(hardware.get("logical_cores") or 1)
    ram = float(hardware.get("ram_gb") or 0)
    if hardware.get("target_ryzen_4600g"):
        return "balanced"
    if logical <= 6 or (ram and ram < 12):
        return "eco"
    if logical >= 20 and ram >= 24:
        return "quality"
    return "balanced"


def resolve_profile(settings: Any, requested: str = "auto", advanced: Any | None = None) -> PerformancePreset:
    hardware = detect_hardware()
    name = (requested or getattr(settings, "performance_profile", "auto") or "auto").lower()
    if name == "auto":
        name = _auto_profile_name(hardware)
    logical = int(hardware["logical_cores"])
    if name == "eco":
        preset = PerformancePreset("eco", "base", "int8", min(4, logical), min(4, logical), 480, 2.5, 1.6, "libx264", "veryfast", 22, 720, 1280, 30, 3)
    elif name == "quality":
        model = "medium" if float(hardware.get("ram_gb") or 0) >= 24 else "small"
        preset = PerformancePreset("quality", model, "int8", min(10, logical), min(10, logical), 720, 6.0, 0.8, "libx264", "medium", 18, 1080, 1920, 30, 5)
    else:
        cpu_threads = min(8, max(4, logical - 4 if logical >= 10 else logical - 2))
        preset = PerformancePreset("balanced", "small", "int8", cpu_threads, min(6, logical), 640, 4.0, 1.2, "libx264", "faster", 20, 1080, 1920, 30, 4)

    values = preset.as_dict()
    configured_model = str(getattr(settings, "whisper_model", "auto") or "auto").lower()
    configured_compute = str(getattr(settings, "whisper_compute_type", "auto") or "auto").lower()
    if configured_model != "auto":
        values["whisper_model"] = configured_model
    if configured_compute != "auto":
        values["compute_type"] = configured_compute
    if int(getattr(settings, "whisper_cpu_threads", 0) or 0) > 0:
        values["cpu_threads"] = int(settings.whisper_cpu_threads)
    if int(getattr(settings, "analysis_width", 0) or 0) > 0:
        values["analysis_width"] = int(settings.analysis_width)
    if str(getattr(settings, "video_preset", "auto") or "auto") != "auto":
        values["ffmpeg_preset"] = str(settings.video_preset)
    if str(getattr(settings, "video_encoder", "auto") or "auto") not in {"", "auto"}:
        values["encoder"] = str(settings.video_encoder)
    if int(getattr(settings, "video_crf", 0) or 0) > 0:
        values["crf"] = int(settings.video_crf)

    if advanced is not None:
        for source_name, target_name in (
            ("whisper_model", "whisper_model"),
            ("compute_type", "compute_type"),
            ("cpu_threads", "cpu_threads"),
            ("analysis_width", "analysis_width"),
            ("ffmpeg_preset", "ffmpeg_preset"),
            ("crf", "crf"),
        ):
            value = getattr(advanced, source_name, None) if not isinstance(advanced, dict) else advanced.get(source_name)
            if value not in (None, 0, "", "auto"):
                values[target_name] = value
        encoder_mode = getattr(advanced, "encoder", "auto") if not isinstance(advanced, dict) else advanced.get("encoder", "auto")
        if encoder_mode == "amd" and "h264_amf" in ffmpeg_encoders():
            values["encoder"] = "h264_amf"
        elif encoder_mode == "cpu":
            values["encoder"] = "libx264"
    if values["encoder"] == "auto":
        values["encoder"] = "libx264"
    return PerformancePreset(**values)


@lru_cache(maxsize=1)
def dependency_report() -> dict[str, Any]:
    return {
        "ffmpeg": _run_version(["ffmpeg", "-version"]) if shutil.which("ffmpeg") else None,
        "ffprobe": _run_version(["ffprobe", "-version"]) if shutil.which("ffprobe") else None,
        "yt_dlp": _run_version([os.sys.executable, "-m", "yt_dlp", "--version"]),
        "deno": _run_version(["deno", "--version"]) if shutil.which("deno") else None,
    }


def _benchmark_encoder(encoder: str, preset: PerformancePreset) -> dict[str, Any]:
    if encoder not in ffmpeg_encoders():
        return {"encoder": encoder, "available": False, "success": False, "reason": "encoder não listado pelo FFmpeg"}
    with tempfile.TemporaryDirectory(prefix="snow-benchmark-") as temporary:
        output = Path(temporary) / f"{encoder}.mp4"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "2",
            "-c:v", encoder,
        ]
        if encoder == "libx264":
            command.extend(["-preset", "veryfast", "-crf", str(preset.crf), "-threads", str(preset.ffmpeg_threads)])
        elif encoder == "h264_amf":
            command.extend(["-quality", "speed", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"])
        command.extend(["-pix_fmt", "yuv420p", str(output)])
        started = time.perf_counter()
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=45, errors="replace")
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"encoder": encoder, "available": True, "success": False, "reason": type(error).__name__}
        elapsed = time.perf_counter() - started
        return {
            "encoder": encoder,
            "available": True,
            "success": result.returncode == 0 and output.is_file() and output.stat().st_size > 0,
            "seconds": round(elapsed, 3),
            "realtime_factor": round(2 / max(0.001, elapsed), 2),
            "reason": "" if result.returncode == 0 else (result.stderr or "falha no FFmpeg")[-500:],
        }


def run_benchmark(settings: Any) -> dict[str, Any]:
    hardware = detect_hardware()
    profile = resolve_profile(settings, "auto")
    results = [_benchmark_encoder("libx264", profile)]
    if "h264_amf" in ffmpeg_encoders():
        results.append(_benchmark_encoder("h264_amf", profile))
    return {
        "hardware": hardware,
        "recommended_profile": profile.as_dict(),
        "encoders": results,
        "recommendation": (
            "Balanced · faster-whisper small · CPU INT8 · um job por vez"
            if hardware.get("target_ryzen_4600g")
            else f"{profile.name.title()} · {profile.whisper_model} · CPU {profile.compute_type}"
        ),
        "hardware_encoding_default": False,
        "note": "A codificação AMD só é usada quando selecionada e aprovada pelo teste; libx264 permanece como fallback seguro.",
    }
