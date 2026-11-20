#!/usr/bin/env bash
# Link the manual test config and the integration into a Home Assistant
# config folder. Existing files are moved to <name>.bak first; existing links
# are replaced.
#
# Usage: dev/manual/link_config.sh [HA_CONFIG_DIR]   (default: ~/ha-dev/config)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
config="$repo/dev/manual/config"
target="${1:-$HOME/ha-dev/config}"

link() {
  local src="$1" dest="$2"
  if [ -L "$dest" ]; then
    rm "$dest"
  elif [ -e "$dest" ]; then
    mv "$dest" "$dest.bak"
    echo "Saved $dest to $dest.bak"
  fi
  ln -s "$src" "$dest"
  echo "$dest -> $src"
}

mkdir -p "$target/custom_components"
link "$config/configuration.yaml" "$target/configuration.yaml"
link "$config/packages" "$target/packages"
link "$config/dashboards" "$target/dashboards"
link "$repo/custom_components/adaptative_climate" "$target/custom_components/adaptative_climate"

# Files included by configuration.yaml but kept local (edited from the UI).
for f in automations.yaml scripts.yaml scenes.yaml; do
  [ -e "$target/$f" ] || echo "[]" > "$target/$f"
done
