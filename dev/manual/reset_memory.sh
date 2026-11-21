#!/usr/bin/env bash
# Forget the memory of entities under test, as on their first start (ENT-DATA-1):
# deletes their stored data, .storage/adaptative_climate.<entry_id> (mode, phase,
# targets, fan/swing memory, and what their sources discovered and keep).
#
# Home Assistant must be stopped: while it runs, it writes its memory back.
# Press "Reset the sources" before stopping it: at the next start, the missing
# targets are taken from the sources as they show them (ENT-TGT-10).
#
# Usage: dev/manual/reset_memory.sh [-c HA_CONFIG_DIR] NAME...   (default: ~/ha-dev/config)
#        dev/manual/reset_memory.sh [-c HA_CONFIG_DIR] --all
#        dev/manual/reset_memory.sh [-c HA_CONFIG_DIR] --list
# NAME: the title of the entry, with or without "Adaptative ", any case
# ("Adaptative BI", "bi", "heat_cool").
set -euo pipefail

config="$HOME/ha-dev/config"
if [ "${1:-}" = "-c" ]; then
  config="${2:?-c needs a folder}"
  shift 2
fi
[ $# -gt 0 ] || { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

storage="$config/.storage"
[ -f "$storage/core.config_entries" ] || { echo "No Home Assistant config in $config" >&2; exit 1; }

# The entries of the integration: "<entry_id><TAB><title>" per line.
entries="$(python3 -I - "$storage/core.config_entries" <<'EOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as file:
    data = json.load(file)
for entry in data["data"]["entries"]:
    if entry["domain"] == "adaptative_climate":
        print(f"{entry['entry_id']}\t{entry['title']}")
EOF
)"

if [ "$1" = "--list" ]; then
  while IFS=$'\t' read -r entry_id title; do
    if [ -f "$storage/adaptative_climate.$entry_id" ]; then memory="memory"; else memory="no memory"; fi
    printf '%-22s %s\n' "$title" "$memory"
  done <<< "$entries"
  exit 0
fi

lock="$config/.ha_run.lock"
if [ -e "$lock" ] && ! flock -n "$lock" true; then
  echo "Home Assistant is running on $config: stop it first (it writes its memory back)." >&2
  exit 1
fi

normalize() {
  local name="${1,,}"
  echo "${name#adaptative }"
}

ids=()
if [ "$1" = "--all" ]; then
  while IFS=$'\t' read -r entry_id _; do ids+=("$entry_id"); done <<< "$entries"
else
  for name in "$@"; do
    found=""
    while IFS=$'\t' read -r entry_id title; do
      [ "$(normalize "$title")" = "$(normalize "$name")" ] && found="$entry_id"
    done <<< "$entries"
    if [ -z "$found" ]; then
      echo "No entry named \"$name\". Entries:" >&2
      cut -f2 <<< "$entries" | sed 's/^/  /' >&2
      exit 1
    fi
    ids+=("$found")
  done
fi

for entry_id in "${ids[@]}"; do
  title="$(grep "^$entry_id"$'\t' <<< "$entries" | cut -f2)"
  file="$storage/adaptative_climate.$entry_id"
  if [ -f "$file" ]; then
    rm "$file"
    echo "$title: memory deleted"
  else
    echo "$title: no memory stored"
  fi
done
