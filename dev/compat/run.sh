#!/usr/bin/env bash
# Run the spec and unit tests on Home Assistant before 2026.11 (ENT-HA-2).
# Creates or updates the venv first. Extra arguments go to pytest.
#
# Usage: dev/compat/run.sh [pytest args]
#   VENV=/path/to/venv (default: ~/ha-dev/.venv-test-2025.1)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
venv="${VENV:-$HOME/ha-dev/.venv-test-2025.1}"
requirements="$repo/dev/compat/requirements.txt"

if [ ! -x "$venv/bin/python" ]; then
  uv python install 3.13
  uv venv "$venv" --python 3.13
fi
uv pip install --quiet --python "$venv/bin/python" -r "$requirements"

cd "$repo"
exec "$venv/bin/pytest" "$@"
