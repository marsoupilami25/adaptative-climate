#!/usr/bin/env python3
"""The copy of the Home Assistant frontend in src/ha (CARD_ARCHITECTURE.md §4, §7).

    ha_copy.py update [TAG]     copy the files of ha-source.json from TAG (default: its
                                source tag), make the mechanical changes, apply the
                                patches, and replace the copy in src/ha
    ha_copy.py make-patch NAME  write ha-patches/NAME.patch: what src/ha changes, compared
                                with the copy made with the patches listed before NAME

The shims of src/ha are ours: never written by this script.
Standard library only, and GNU patch.
"""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

FRONTEND = Path(__file__).resolve().parents[1]
SOURCE = FRONTEND / "ha-source.json"
COPY = FRONTEND / "src" / "ha"
PATCHES = FRONTEND / "ha-patches"
RAW = "https://raw.githubusercontent.com/{repository}/{tag}/{path}"

NOTICE = """\
This folder holds a copy of files of the Home Assistant frontend
(https://github.com/{repository}), tag {tag},
Copyright the Home Assistant authors, licensed under the Apache License 2.0
(https://www.apache.org/licenses/LICENSE-2.0).

Changes made to the copied files (CARD_ARCHITECTURE.md §4):
- the tag names of the copied elements get the prefix "{prefix}";
- the imports of the elements of Home Assistant used as they are are removed;
- the patches of frontend/ha-patches: {patches}.

The files listed as shims in frontend/ha-source.json are not copied: they are
written for the card, and hold only what the copied files need.
"""


def load() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def local(path: str) -> str:
    """The path of a frontend file inside src/ha: without its leading src/."""
    return path.removeprefix("src/")


def fetch(source: dict, tag: str, out: Path) -> None:
    for path in source["files"]:
        url = RAW.format(repository=source["repository"], tag=tag, path=path)
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read()
        target = out / local(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def mechanical(source: dict, out: Path) -> None:
    """The prefix on the copied elements; no import of the elements used as is."""
    names = "|".join(re.escape(name) for name in source["prefixed_elements"])
    # A tag name, opening or closing, not a path ("../components/ha-big-number")
    # nor a longer name
    closing = re.compile(rf"</({names})(?![\w-])")
    element = re.compile(rf"(?<![\w/.-])({names})(?![\w-])")
    used = "|".join(re.escape(name) for name in source["used_as_is"])
    side_effect_import = re.compile(rf'^import "[./]*(?:components/)?(?:{used})";\n', re.M)
    for path in source["files"]:
        file = out / local(path)
        text = file.read_text(encoding="utf-8")
        text = closing.sub(lambda m: "</" + source["prefix"] + m.group(1), text)
        text = element.sub(lambda m: source["prefix"] + m.group(1), text)
        text = side_effect_import.sub("", text)
        left = re.findall(rf"</?(?:{names})(?![\w-])", text)
        if left:
            sys.exit(f"{path}: tags left without the prefix: {sorted(set(left))}")
        file.write_text(text, encoding="utf-8")


def apply_patches(names: list[str], out: Path) -> None:
    for name in names:
        patch = PATCHES / f"{name}.patch"
        result = subprocess.run(
            ["patch", "-p1", "--forward", "--batch", "--no-backup-if-mismatch", "-d", str(out), "-i", str(patch)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            sys.exit(f"Patch {name} does not apply:\n{result.stdout}{result.stderr}")


def stage(source: dict, tag: str, patches: list[str], out: Path) -> None:
    fetch(source, tag, out)
    mechanical(source, out)
    apply_patches(patches, out)


def update(tag: str | None) -> None:
    source = load()
    tag = tag or source["source_tag"]
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        stage(source, tag, source["patches"], staged)
        shims = {local(path) for path in source["shims"]}
        if COPY.exists():
            for file in COPY.rglob("*.ts"):
                if file.relative_to(COPY).as_posix() not in shims:
                    file.unlink()
        for path in source["files"]:
            target = COPY / local(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged / local(path), target)
    (COPY / "NOTICE").write_text(
        NOTICE.format(
            repository=source["repository"],
            tag=tag,
            prefix=source["prefix"],
            patches=", ".join(source["patches"]) or "none",
        ),
        encoding="utf-8",
    )
    if tag != source["source_tag"]:
        source["source_tag"] = tag
        SOURCE.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"src/ha: {len(source['files'])} files from {source['repository']} {tag}")


def make_patch(name: str) -> None:
    source = load()
    if name in source["patches"] and source["patches"][-1] != name:
        sys.exit(f"{name} is not the last patch: only the last one can be written again")
    before = [patch for patch in source["patches"] if patch != name]
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        stage(source, source["source_tag"], before, staged)
        diff: list[str] = []
        for path in source["files"]:
            rel = local(path)
            old = (staged / rel).read_text(encoding="utf-8").splitlines(keepends=True)
            new = (COPY / rel).read_text(encoding="utf-8").splitlines(keepends=True)
            diff += difflib.unified_diff(old, new, f"a/{rel}", f"b/{rel}")
    if not diff:
        sys.exit(f"No change in src/ha compared with the patches before {name}")
    PATCHES.mkdir(exist_ok=True)
    (PATCHES / f"{name}.patch").write_text("".join(diff), encoding="utf-8")
    if name not in source["patches"]:
        source["patches"].append(name)
        SOURCE.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"ha-patches/{name}.patch written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("update").add_argument("tag", nargs="?")
    commands.add_parser("make-patch").add_argument("name")
    args = parser.parse_args()
    if args.command == "update":
        update(args.tag)
    else:
        make_patch(args.name)


if __name__ == "__main__":
    main()
