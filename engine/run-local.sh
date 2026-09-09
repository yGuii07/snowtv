#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "FFmpeg e ffprobe precisam estar instalados e disponíveis no PATH."
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "O ambiente ainda não foi preparado. Execute ./setup-local.sh uma única vez."
  exit 1
fi

if ! command -v deno >/dev/null 2>&1; then
  echo "Aviso: Deno não encontrado. O yt-dlp continuará com fallback quando necessário."
fi

exec .venv/bin/python -m uvicorn snow_engine.api:app --host 0.0.0.0 --port 8000 --workers 1
