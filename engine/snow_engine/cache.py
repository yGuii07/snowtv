from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CachedSource:
    content_hash: str
    path: Path


class CacheManager:
    def __init__(self, root: Path, enabled: bool = True):
        self.root = root
        self.enabled = enabled
        for name in ("media", "urls", "metadata", "transcripts", "selections", "proxies", "tracking"):
            (root / name).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(8 * 1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _link_or_copy(source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
        return destination

    def source_for_url(self, url: str) -> CachedSource | None:
        if not self.enabled:
            return None
        mapping = self._read_json(self.root / "urls" / f"{self._key(url)}.json")
        if not mapping:
            return None
        path = self.root / "media" / str(mapping.get("filename") or "")
        content_hash = str(mapping.get("content_hash") or "")
        if not content_hash or not path.is_file():
            return None
        return CachedSource(content_hash, path)

    def materialize_source(self, cached: CachedSource, job_dir: Path) -> Path:
        return self._link_or_copy(cached.path, job_dir / f"source-cache{cached.path.suffix.lower()}")

    def register_source(self, source: Path, source_ref: str = "", source_kind: str = "") -> CachedSource:
        content_hash = self.file_hash(source)
        if not self.enabled:
            return CachedSource(content_hash, source)
        suffix = source.suffix.lower() or ".mp4"
        filename = f"{content_hash}{suffix}"
        cached_path = self.root / "media" / filename
        if not cached_path.is_file():
            self._link_or_copy(source, cached_path)
        if source_kind == "url" and source_ref:
            self._write_json(
                self.root / "urls" / f"{self._key(source_ref)}.json",
                {"content_hash": content_hash, "filename": filename},
            )
        return CachedSource(content_hash, cached_path)

    def transcript_path(self, content_hash: str, language: str, model: str) -> Path:
        key = self._key(json.dumps([content_hash, language, model], separators=(",", ":")))
        return self.root / "transcripts" / f"{key}.json"

    def metadata_path(self, content_hash: str) -> Path:
        return self.root / "metadata" / f"{content_hash}.json"

    def selection_path(self, content_hash: str, options: dict[str, Any]) -> Path:
        key = self._key(content_hash + json.dumps(options, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return self.root / "selections" / f"{key}.json"

    def proxy_path(self, content_hash: str, width: int) -> Path:
        return self.root / "proxies" / f"{content_hash}-{width}w.mp4"

    def tracking_path(self, content_hash: str, options: dict[str, Any]) -> Path:
        key = self._key(content_hash + json.dumps(options, sort_keys=True, separators=(",", ":")))
        return self.root / "tracking" / f"{key}.json"

    def load_json(self, path: Path) -> dict[str, Any] | list[Any] | None:
        return self._read_json(path) if self.enabled else None

    def save_json(self, path: Path, value: Any) -> None:
        if self.enabled:
            self._write_json(path, value)

    @staticmethod
    def _read_json(path: Path) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
