from __future__ import annotations

import json
import re
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .captions import caption_presets_payload
from .config import settings
from .hardware import dependency_report, detect_hardware, ffmpeg_encoders, resolve_profile, run_benchmark
from .media import dependencies_available
from .models import ClipFeedbackRequest, HealthResponse, JobCreated, ProcessOptions, ProcessRequest
from .pipeline import Pipeline
from .queue import JobQueue
from .selector import HighlightSelector
from .store import JobStore
from .transcription import Transcriber


store = JobStore(settings.database_path)
transcriber = Transcriber(settings)
selector = HighlightSelector(settings)
pipeline = Pipeline(settings, store, transcriber, selector)
queue = JobQueue(store, pipeline, settings.worker_concurrency)
bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    queue.recover()
    yield
    queue.shutdown()


app = FastAPI(
    title="Snow Engine",
    description="Motor self-hosted do SnowTV para transcrição, seleção, reenquadramento e renderização.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["Content-Length", "Content-Disposition"],
)


@app.middleware("http")
async def private_network_access(request: Request, call_next: Any):
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network", "").lower() == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


def require_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> None:
    if not settings.api_token:
        return
    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    if not secrets.compare_digest(supplied, settings.api_token):
        raise HTTPException(status_code=401, detail="Token do Snow Engine inválido.")


def _is_supported_youtube(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return parsed.scheme == "https" and (host in {"youtu.be", "youtube.com", "m.youtube.com"} or host.endswith(".youtube.com"))


def _base_url(request: Request) -> str:
    return (settings.public_base_url.strip() or str(request.base_url)).rstrip("/")


def _public_job(job: dict[str, Any], request: Request) -> dict[str, Any]:
    result = job.get("result")
    if result:
        result = json.loads(json.dumps(result))
        base = _base_url(request)
        for clip in result.get("clips", []):
            for field in ("video_url", "download_url"):
                value = clip.get(field)
                if not isinstance(value, str):
                    continue
                path, separator, query = value.partition("?")
                if path.startswith("/"):
                    parameters = {"media_token": job["media_token"]}
                    if query:
                        parameters.update(dict(item.split("=", 1) for item in query.split("&") if "=" in item))
                    clip[field] = f"{base}{path}?{urlencode(parameters)}"
    return {
        "job_id": job["job_id"],
        "id": job["job_id"],
        "status": job["status"],
        "state": job["stage"] if job["status"] == "processing" else job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "error": job.get("error"),
        "logs": [entry.get("message", "") for entry in job.get("logs", [])],
        "log_entries": job.get("logs", []),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "result": result,
        "clips": result.get("clips", []) if result else [],
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    ffmpeg, ffprobe = dependencies_available()
    hardware = detect_hardware()
    profile = resolve_profile(settings, "auto")
    device, compute = transcriber._device_and_compute_type(profile)
    dependencies = dependency_report()
    encoders = [name for name in ("libx264", "h264_amf", "h264_nvenc", "h264_videotoolbox") if name in ffmpeg_encoders()]
    return HealthResponse(
        status="ok" if ffmpeg and ffprobe and dependencies.get("yt_dlp") else "degraded",
            ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        transcription=f"faster-whisper:{profile.whisper_model}:{device}:{compute}",
        selection=(f"llm:{settings.llm_provider}:{settings.llm_model}" if settings.llm_model else "heuristic:local"),
        face_tracking="opencv-csrt+haar",
        queue_workers=settings.worker_concurrency,
        hardware=hardware,
        dependencies=dependencies,
        profile=profile.as_dict(),
        encoders=encoders,
        runtime={
            "workers": settings.worker_concurrency,
            "cache_enabled": settings.cache_enabled,
            "projects_dir": str(settings.jobs_dir),
        },
    )


@app.get("/api/capabilities", dependencies=[Depends(require_token)])
def capabilities() -> dict[str, Any]:
    return {
        "caption_presets": caption_presets_payload(),
        "profiles": ["auto", "eco", "balanced", "quality"],
        "editorial_styles": ["auto", "viral", "educational", "podcast", "storytelling", "commentary"],
        "selector_version": 5,
        "encoders": [name for name in ("libx264", "h264_amf", "h264_nvenc") if name in ffmpeg_encoders()],
    }


@app.post("/api/benchmark", dependencies=[Depends(require_token)])
def benchmark() -> dict[str, Any]:
    return run_benchmark(settings)


@app.post("/api/process", response_model=JobCreated, status_code=202, dependencies=[Depends(require_token)])
def process_url(payload: ProcessRequest) -> JobCreated:
    source_url = str(payload.url)
    if not _is_supported_youtube(source_url):
        raise HTTPException(status_code=400, detail="Use um link HTTPS válido do YouTube.")
    job_id = uuid.uuid4().hex
    options = payload.model_dump(by_alias=True, exclude={"url", "acknowledged"})
    store.create(job_id, "url", source_url, options)
    queue.submit(job_id)
    return JobCreated(job_id=job_id)


@app.post("/api/process/upload", response_model=JobCreated, status_code=202, dependencies=[Depends(require_token)])
async def process_upload(
    file: Annotated[UploadFile, File(description="Arquivo de vídeo")],
    options: Annotated[str, Form()] = "{}",
) -> JobCreated:
    try:
        parsed_options = ProcessOptions.model_validate_json(options)
    except Exception as error:
        raise HTTPException(status_code=422, detail="As opções do processamento são inválidas.") from error
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}:
        raise HTTPException(status_code=415, detail="Formato não suportado. Envie MP4, MOV, MKV, AVI ou WebM.")

    job_id = uuid.uuid4().hex
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    destination = job_dir / f"source-upload{suffix}"
    store.create(
        job_id,
        "upload",
        file.filename or destination.name,
        parsed_options.model_dump(by_alias=True),
        str(destination),
    )
    maximum_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with destination.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > maximum_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"O arquivo excede o limite configurado de {settings.max_upload_mb} MB.",
                    )
                target.write(chunk)
    except Exception as error:
        destination.unlink(missing_ok=True)
        message = error.detail if isinstance(error, HTTPException) else "Falha ao salvar o upload."
        store.update(job_id, status="failed", progress=100, stage="failed", error=str(message))
        raise
    finally:
        await file.close()
    queue.submit(job_id)
    return JobCreated(job_id=job_id)


@app.get("/api/status/{job_id}", dependencies=[Depends(require_token)])
def job_status(job_id: str, request: Request) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Código de processamento inválido.")
    try:
        return _public_job(store.get(job_id), request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Processamento não encontrado.") from error


@app.get("/api/jobs", dependencies=[Depends(require_token)])
def jobs(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 30) -> dict[str, Any]:
    return {"jobs": [_public_job(job, request) for job in store.list(limit)]}


@app.post("/api/jobs/{job_id}/rerender", response_model=JobCreated, status_code=202, dependencies=[Depends(require_token)])
def rerender(job_id: str, payload: ProcessOptions) -> JobCreated:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Código de projeto inválido.")
    try:
        original = store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Projeto original não encontrado.") from error
    source_path = Path(str(original.get("source_path") or ""))
    source_kind = "reuse" if source_path.is_file() else original["source_kind"]
    if source_kind != "reuse" and original["source_kind"] != "url":
        raise HTTPException(status_code=409, detail="O arquivo original não está mais disponível para rerenderizar.")
    new_job_id = uuid.uuid4().hex
    rerender_options = payload.model_dump(by_alias=True)
    source_hash = str((original.get("result") or {}).get("source_hash") or "")
    if len(source_hash) == 64:
        rerender_options["_sourceHash"] = source_hash
    store.create(
        new_job_id,
        source_kind,
        original["source_ref"],
        rerender_options,
        str(source_path) if source_path.is_file() else None,
    )
    store.append_log(new_job_id, f"Rerenderização criada a partir do projeto {job_id[:8]}; caches serão reutilizados.")
    queue.submit(new_job_id)
    return JobCreated(job_id=new_job_id)


@app.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(require_token)])
def cancel_job(job_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Código de projeto inválido.")
    try:
        cancelled = queue.cancel(job_id)
        job = store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.") from error
    if not cancelled:
        raise HTTPException(status_code=409, detail=f"O job já está no estado {job['status']}.")
    return {"cancelled": True, "job_id": job_id, "status": "cancelled"}


@app.post("/api/jobs/{job_id}/resume", response_model=JobCreated, status_code=202, dependencies=[Depends(require_token)])
def resume_job(job_id: str) -> JobCreated:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Código de projeto inválido.")
    try:
        queue.resume(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return JobCreated(job_id=job_id)


@app.post("/api/jobs/{job_id}/feedback", dependencies=[Depends(require_token)])
def save_clip_feedback(job_id: str, payload: ClipFeedbackRequest) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Código de projeto inválido.")
    try:
        feedback = store.save_feedback(job_id, payload.clip_index, payload.rating, payload.reasons)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.") from error
    return {"saved": True, "feedback": feedback}


@app.get("/api/jobs/{job_id}/feedback", dependencies=[Depends(require_token)])
def clip_feedback(job_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Código de projeto inválido.")
    try:
        store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.") from error
    return {"feedback": store.feedback(job_id)}


@app.delete("/api/jobs/{job_id}", dependencies=[Depends(require_token)])
def delete_job(job_id: str) -> dict[str, bool]:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Código de projeto inválido.")
    try:
        job = store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.") from error
    if job["status"] not in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Aguarde o job terminar antes de excluí-lo.")
    store.delete(job_id)
    job_dir = (settings.jobs_dir / job_id).resolve()
    jobs_root = settings.jobs_dir.resolve()
    if job_dir.parent == jobs_root and job_dir.name == job_id:
        shutil.rmtree(job_dir, ignore_errors=True)
    return {"deleted": True}


@app.get("/media/{job_id}/{filename}")
def media(
    job_id: str,
    filename: str,
    media_token: str = Query(default=""),
    download: bool = Query(default=False),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id) or not re.fullmatch(r"clip-\d{2}\.mp4", filename):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    try:
        job = store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.") from error
    bearer_token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    valid_job_token = bool(media_token) and secrets.compare_digest(media_token, job["media_token"])
    valid_api_token = bool(settings.api_token) and secrets.compare_digest(bearer_token, settings.api_token)
    if not valid_job_token and not valid_api_token:
        raise HTTPException(status_code=401, detail="Link de mídia inválido ou expirado.")
    path = settings.jobs_dir / job_id / "clips" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename if download else None,
        content_disposition_type="attachment" if download else "inline",
    )
