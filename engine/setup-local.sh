#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "FFmpeg e ffprobe precisam estar instalados e disponíveis no PATH."
  exit 1
fi

python_command=""
for candidate in python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in [(3,11),(3,12)] else 1)' 2>/dev/null; then
    python_command="$candidate"
    break
  fi
done
if [[ -z "$python_command" ]]; then
  echo "Python 3.11 ou 3.12 não foi encontrado."
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  "$python_command" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --upgrade -r requirements.txt
.venv/bin/python -c 'import cv2, fastapi, faster_whisper, yt_dlp; print("Dependências Python OK")'

echo "Ambiente pronto. Use ./run-local.sh nas próximas inicializações."
