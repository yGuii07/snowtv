from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SNOW_",
        env_file=(".env", "engine/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("./data")
    api_token: str = ""
    public_base_url: str = ""
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"
    max_upload_mb: int = 4096
    max_video_minutes: int = 240
    worker_concurrency: int = 1
    performance_profile: str = "auto"
    cache_enabled: bool = True
    cache_dir: Path | None = None

    whisper_model: str = "auto"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_cpu_threads: int = 0

    llm_provider: str = "heuristic"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_timeout_seconds: int = 60

    face_sample_fps: float = 6.0
    face_redetect_seconds: float = 1.0
    analysis_width: int = 0
    video_encoder: str = "auto"
    video_preset: str = "auto"
    video_crf: int = 0
    output_width: int = 1080
    output_height: int = 1920
    output_fps: int = 30
    ytdlp_cookies_file: str = ""
    ytdlp_format: str = "bv*+ba/b"
    ytdlp_fallback_format: str = "b[height<=1080][ext=mp4]/b[height<=1080]/b/bv*+ba"
    ytdlp_fallback_player_clients: str = "default,-web_safari"
    ytdlp_js_runtime: str = "auto"
    ytdlp_js_runtime_path: str = ""
    ytdlp_remote_components: bool = False

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "snow-engine.sqlite3"

    @property
    def resolved_cache_dir(self) -> Path:
        return self.cache_dir or self.data_dir / "cache"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_cache_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.prepare()
