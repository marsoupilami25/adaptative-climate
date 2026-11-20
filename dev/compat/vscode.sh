#!/usr/bin/env bash
# Shows the compatibility tests (Home Assistant 2025.1.0) in the VS Code
# Testing tab, next to the current ones. To run once per dev environment;
# running it again does no harm. See dev/compat/README.md.
#
# VS Code runs the tests of a workspace folder with a single venv. This makes a
# second folder, outside the repo, whose contents are links to the repo and
# whose venv is the compatibility one, and adds it to the workspace.
#
# Usage: dev/compat/vscode.sh
#   FOLDER=...    (default: ~/ha-dev/adaptative-climate-2025.1)
#   WORKSPACE=... (default: ~/ha-dev/ha-dev.code-workspace)
#   VENV=...      (default: ~/ha-dev/.venv-test-2025.1)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
folder="${FOLDER:-$HOME/ha-dev/adaptative-climate-2025.1}"
workspace="${WORKSPACE:-$HOME/ha-dev/ha-dev.code-workspace}"

. "$repo/dev/compat/venv.sh"

# What the tests need from the repo. Add here any other top-level item they
# come to use.
mkdir -p "$folder/.vscode"
for item in custom_components dev pyproject.toml; do
  ln -sfn "$repo/$item" "$folder/$item"
done

# The test paths are given explicitly: through the links, pytest's testpaths
# misses the --spec-rules option of dev/spec/conftest.py. search.exclude keeps
# the files out of Search and Quick Open, where they would show twice.
cat > "$folder/.vscode/settings.json" <<EOF
{
  "python.defaultInterpreterPath": "$venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": ["dev/spec", "dev/unit"],
  "search.exclude": {"**": true}
}
EOF

if [ -f "$workspace" ] && python3 - "$workspace" "$folder" <<'PY'
import json
import sys

path, folder = sys.argv[1:]
with open(path, encoding="utf-8") as file:
    workspace = json.load(file)
folders = workspace.setdefault("folders", [])
if all(entry.get("path") != folder for entry in folders):
    folders.append({"name": "adaptative-climate (HA 2025.1)", "path": folder})
    with open(path, "w", encoding="utf-8") as file:
        json.dump(workspace, file, indent=2)
        file.write("\n")
PY
then
  echo "$folder is in $workspace."
else
  echo "Add $folder to the workspace: File > Add Folder to Workspace..."
fi
echo "Then, in VS Code: Developer: Reload Window."
