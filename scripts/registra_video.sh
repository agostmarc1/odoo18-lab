#!/usr/bin/env bash
# Registra il video dimostrativo dell'app (vedi scripts/registra_video.py).
# Richiede: Odoo avviato su http://127.0.0.1:8069, Google Chrome, ffmpeg.
# La prima volta crea l'ambiente Python .venv-video con Playwright (gitignored).
#   ./scripts/registra_video.sh           -> registra il video
#   ./scripts/registra_video.sh --prova   -> solo schermate di controllo
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv-video/Scripts/python
[ -x "$PY" ] || PY=.venv-video/bin/python
if [ ! -x "$PY" ]; then
  python -m venv .venv-video
  PY=.venv-video/Scripts/python; [ -x "$PY" ] || PY=.venv-video/bin/python
  "$PY" -m pip install -q "playwright==1.65.0"
fi
"$PY" scripts/registra_video.py "$@"
