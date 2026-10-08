#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if [ ! -x .venv/bin/python ]; then
  echo 'Install the Python environment described in README.md first.'
  exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm install && npm run build)
fi
exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "${ORBIT_PORT:-8001}"
