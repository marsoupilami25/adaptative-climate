#!/usr/bin/env python3
"""What the card needs from the Home Assistant frontend that hosts it (CARD_ARCHITECTURE.md §7).

Lists what src/ha (the copy) and src/ac (the AC code) use from the host frontend,
and checks it exists in the minimum frontend of ha-source.json:

- the contexts consumed (defined, provided) and the members used;
- the --ha-* CSS variables used without a fallback;
- the members of `hass` used;
- the translation keys;
- the elements used as is: defined, and with the same public interface in the
  minimum frontend as in the source tag: properties, events, and documented CSS
  variables (@cssprop). Their inner styles are theirs: not compared;
- the calls to the backend (listed, to review).

Exits with 1 when something is missing. The sources of both frontends are
downloaded once into frontend/.cache. Standard library only.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import urllib.request

FRONTEND = Path(__file__).resolve().parents[1]
SOURCE = json.loads((FRONTEND / "ha-source.json").read_text(encoding="utf-8"))
CACHE = FRONTEND / ".cache"
TARBALL = "https://codeload.github.com/{repository}/tar.gz/refs/tags/{tag}"

missing: list[str] = []


def frontend_src(tag: str) -> Path:
    """The src/ folder of the frontend at that tag, downloaded once."""
    folder = CACHE / f"frontend-{tag}"
    if not (folder / "src").is_dir():
        CACHE.mkdir(exist_ok=True)
        url = TARBALL.format(repository=SOURCE["repository"], tag=tag)
        with tempfile.TemporaryFile() as archive:
            with urllib.request.urlopen(url, timeout=120) as response:
                while chunk := response.read(1 << 20):
                    archive.write(chunk)
            archive.seek(0)
            with tarfile.open(fileobj=archive, mode="r:gz") as tar:
                members = []
                for member in tar.getmembers():
                    parts = member.name.split("/", 1)
                    if len(parts) == 2 and parts[1].startswith("src/"):
                        member.name = parts[1]
                        members.append(member)
                tar.extractall(folder, members=members, filter="data")
    return folder / "src"


def read_all(folder: Path) -> dict[Path, str]:
    return {file: file.read_text(encoding="utf-8") for file in folder.rglob("*.ts")} if folder.is_dir() else {}


def check(ok: bool, what: str) -> None:
    print(f"  {'ok     ' if ok else 'MISSING'} {what}")
    if not ok:
        missing.append(what)


def main() -> None:
    minimum = frontend_src(SOURCE["minimum_tag"])
    source = frontend_src(SOURCE["source_tag"])
    ours = read_all(FRONTEND / "src" / "ha") | read_all(FRONTEND / "src" / "ac")
    text = "\n".join(ours.values())
    min_text = "\n".join(file.read_text(encoding="utf-8") for file in minimum.rglob("*.ts"))
    min_types = (minimum / "types.ts").read_text(encoding="utf-8")
    print(f"Minimum frontend {SOURCE['minimum_tag']} (Home Assistant {SOURCE['minimum_home_assistant']}),"
          f" source tag {SOURCE['source_tag']}")

    print("Contexts")
    shim = (FRONTEND / "src" / "ha" / "data" / "context" / "index.ts").read_text(encoding="utf-8")
    min_contexts = (minimum / "data" / "context" / "index.ts").read_text(encoding="utf-8")
    min_mixin = (minimum / "state" / "context-mixin.ts").read_text(encoding="utf-8")
    for content in ours.values():
        for m in re.finditer(r"@consume\(\{\s*context:\s*(\w+)[\s\S]*?\}\)\s*(?:@\w+\([^)]*\)\s*)*(?:private|protected|public)?\s*(\w+)", content):
            name, prop = m.groups()
            key = re.search(rf'export const {name}\s*=\s*createContext<[^>]*>\(\s*"([^"]+)"', shim)
            check(bool(key) and f'"{key.group(1)}"' in min_contexts and name in min_mixin,
                  f"context {name} ({key.group(1) if key else '?'}): defined and provided")
            for member in sorted(set(re.findall(rf"this\.{prop}\??\.(\w+)", content))):
                check(re.search(rf"^\s+{member}\??[:(<]", min_types, re.M) is not None, f"  member {prop}.{member}")

    print("CSS variables --ha-* without a fallback")
    for var in sorted(set(re.findall(r"var\(\s*(--ha-[a-z0-9-]+)\s*\)", text))):
        check(re.search(re.escape(var) + r"\s*:", min_text) is not None, var)

    print("Members of hass")
    for member in sorted(set(re.findall(r"\bhass!?\??\.(\w+)", text))):
        check(re.search(rf"^\s+{member}\??[:(<]", min_types, re.M) is not None, f"hass.{member}")

    print("Translation keys")
    en = json.loads((minimum / "translations" / "en.json").read_text(encoding="utf-8"))
    for key in sorted(set(re.findall(r'"(ui\.[a-z0-9_.-]+)"', text))):
        node = en
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        fallback = SOURCE.get("compat_fallbacks", {}).get(key)
        if node is None and fallback:
            print(f"  patch   {key}: not in the minimum, fallback in the patch {fallback}")
            continue
        check(node is not None, key)

    print("Elements used as is")
    used_in_templates = set(re.findall(r"<((?:ha|hui)-[a-z0-9-]+)", text))
    for element in sorted(used_in_templates):
        check(element in SOURCE["used_as_is"], f"<{element}> is listed in used_as_is")
    for element, path in sorted(SOURCE["used_as_is"].items()):
        min_file = minimum / path.removeprefix("src/")
        src_file = source / path.removeprefix("src/")
        check(min_file.is_file() and f'"{element}"' in min_file.read_text(encoding="utf-8"), f"<{element}> defined")
        if not (min_file.is_file() and src_file.is_file()):
            continue
        old, new = min_file.read_text(encoding="utf-8"), src_file.read_text(encoding="utf-8")
        for kind, pattern in (
            ("property", r"@property\([^)]*\)\s*(?:public\s+)?(\w+)"),
            ("event", r'fireEvent\(\s*this,\s*"([a-z-]+)"'),
            ("documented CSS variable", r"@cssprop\s+(--[a-z0-9-]+)"),
        ):
            for name in sorted(set(re.findall(pattern, new)) - set(re.findall(pattern, old))):
                check(False, f"<{element}> {kind} {name}: in the source tag, not in the minimum")

    print("Calls to the backend (to review)")
    for file, content in sorted(ours.items()):
        for call in sorted(set(re.findall(r"\b(callService|callWS|callApi|sendMessagePromise|subscribeMessage)\(", content))):
            print(f"  {call:20s} {file.relative_to(FRONTEND)}")

    if missing:
        sys.exit(f"\n{len(missing)} missing in the minimum frontend")
    print("\nAll present in the minimum frontend.")


if __name__ == "__main__":
    main()
