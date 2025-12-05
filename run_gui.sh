#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found in PATH." >&2
  echo "Install instructions: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating uv-managed virtual environment..."
  uv venv
fi

echo "Syncing dependencies with uv..."
uv sync --locked

PY_MAC=".venv/bin/python"
if [ ! -x "$PY_MAC" ]; then
  echo "Expected interpreter not found at $PY_MAC" >&2
  exit 1
fi

exec "$PY_MAC" -m openai_tts_gui "$@"
