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

# Expander Card (MelleD/lovelace-expander-card), for the views Expander and
# Expander 2 (CARD-LOOK-9): downloaded once here into www/, loaded by the
# package card_tests.yaml (frontend: extra_module_url). To update, change the
# version here and in the package, and delete www/expander-card.js.
expander_version="7.3.7"
if [ ! -e "$target/www/expander-card.js" ]; then
  mkdir -p "$target/www"
  curl -fsSL -o "$target/www/expander-card.js" \
    "https://github.com/MelleD/lovelace-expander-card/releases/download/$expander_version/expander-card.js"
  echo "$target/www/expander-card.js: Expander Card $expander_version"
fi

if [ ! -e "$repo/custom_components/adaptative_climate/frontend/adaptative-climate-card.js" ]; then
  echo "The card is not built: cd frontend && npm run build (see dev/README.md)"
fi
