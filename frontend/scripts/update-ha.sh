#!/usr/bin/env bash
# Copies the files of the Home Assistant frontend listed in ha-source.json into
# src/ha, from a tag (default: the source tag of ha-source.json), with the
# mechanical changes and the patches; then checks what the copy needs from the
# minimum frontend. See CARD_ARCHITECTURE.md §7.
#
# Usage: scripts/update-ha.sh [TAG]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 ha_copy.py update "$@"
python3 compat-scan.py
