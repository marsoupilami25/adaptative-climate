#!/usr/bin/env bash
# Link the manual tests of the card into a Home Assistant config folder: its
# package (which declares the dashboard "Tests card") and its dashboard. The
# data are the entities of the manual tests of the integration: run
# tests/integration/manual/link_config.sh first, then this script.
#
# Usage: tests/card/manual/link_config.sh [HA_CONFIG_DIR]   (default: ~/ha-dev/config)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
config="$repo/tests/card/manual/config"
target="${1:-$HOME/ha-dev/config}"

for folder in packages dashboards; do
  if [ -L "$target/$folder" ] || [ ! -d "$target/$folder" ]; then
    echo "$target/$folder is not a folder: run tests/integration/manual/link_config.sh first" >&2
    exit 1
  fi
done

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

link "$config/packages/card_tests.yaml" "$target/packages/card_tests.yaml"
link "$config/dashboards/card_tests.yaml" "$target/dashboards/card_tests.yaml"

if [ ! -e "$repo/custom_components/adaptative_climate/frontend/adaptative-climate-card.js" ]; then
  echo "The card is not built: cd frontend && npm run build (see dev/README.md)"
fi
