# Creates or updates the compatibility venv. Sourced by run.sh and vscode.sh,
# which set $repo; sets $venv.
#   VENV=/path/to/venv (default: ~/ha-dev/.venv-test-2025.1)

venv="${VENV:-$HOME/ha-dev/.venv-test-2025.1}"

if [ ! -x "$venv/bin/python" ]; then
  uv python install 3.13
  uv venv "$venv" --python 3.13
fi
uv pip install --quiet --python "$venv/bin/python" -r "$repo/dev/compat/requirements.txt"
