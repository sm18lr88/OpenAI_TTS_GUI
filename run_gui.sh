#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found in PATH." >&2
  echo "Install: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

exec uv run python -m openai_tts_gui "$@"
