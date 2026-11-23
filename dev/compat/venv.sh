# Creates or updates the compatibility venv. Sourced by run.sh and vscode.sh,
# which set $repo; sets $venv.
#   VENV=/path/to/venv (default: ~/ha-dev/.venv-test-2026.6)

venv="${VENV:-$HOME/ha-dev/.venv-test-2026.6}"

if [ ! -x "$venv/bin/python" ]; then
  uv python install 3.14
  uv venv "$venv" --python 3.14
fi
uv pip install --quiet --python "$venv/bin/python" -r "$repo/dev/compat/requirements.txt"
