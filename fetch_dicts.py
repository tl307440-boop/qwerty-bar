"""Build the local dictionary catalog from the upstream qwerty-learner repo.

Usage:
    python fetch_dicts.py                 # refresh catalog + download the default dicts
    python fetch_dicts.py ielts cet4      # also download these dictionary ids
    python fetch_dicts.py --all           # download everything (~90MB, slow)
    python fetch_dicts.py --list          # print available dictionary ids
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = "RealKai42/qwerty-learner"
BRANCH = "master"
MIRRORS = (
    f"https://cdn.jsdelivr.net/gh/{REPO}@{BRANCH}",
    f"https://raw.githubusercontent.com/{REPO}/{BRANCH}",
    f"https://gcore.jsdelivr.net/gh/{REPO}@{BRANCH}",
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DICT_DIR = DATA / "dicts"
CATALOG = DATA / "catalog.json"

DEFAULT_DICTS = ["cet4", "cet6", "ielts", "kaoyan", "coder"]

_FIELD = {
    "id": r"id:\s*'([^']*)'",
    "name": r"name:\s*'([^']*)'",
    "description": r"description:\s*'([^']*)'",
    "category": r"category:\s*'([^']*)'",
    "url": r"url:\s*'([^']*)'",
    "length": r"length:\s*(\d+)",
    "language": r"language:\s*'([^']*)'",
    "languageCategory": r"languageCategory:\s*'([^']*)'",
}


def download(path: str, timeout: int = 60) -> bytes:
    """Fetch a repo-relative path, trying each mirror in turn."""
    last = None
    for base in MIRRORS:
        try:
            req = urllib.request.Request(f"{base}/{path}", headers={"User-Agent": "qwerty-bar"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - any mirror failure falls through
            last = exc
    raise RuntimeError(f"all mirrors failed for {path}: {last}")


def parse_dictionary_ts(source: str) -> list[dict]:
    # Drop commented-out entries so they do not end up in the catalog.
    source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//"))

    entries = []
    for match in re.finditer(r"id:\s*'", source):
        start = source.rfind("{", 0, match.start())
        depth, end = 0, -1
        for i in range(start, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            continue
        block = source[start : end + 1]
        item = {}
        for key, pattern in _FIELD.items():
            found = re.search(pattern, block)
            if found:
                item[key] = int(found.group(1)) if key == "length" else found.group(1)
        if {"id", "name", "url"} <= item.keys():
            item.setdefault("length", 0)
            item["file"] = item["url"].rsplit("/", 1)[-1]
            entries.append(item)
    return entries


def refresh_catalog() -> list[dict]:
    DATA.mkdir(parents=True, exist_ok=True)
    source = download("src/resources/dictionary.ts").decode("utf-8")
    entries = parse_dictionary_ts(source)
    if not entries:
        raise RuntimeError("parsed 0 dictionaries; upstream format may have changed")
    CATALOG.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"catalog: {len(entries)} dictionaries -> {CATALOG}")
    return entries


def fetch_dict(entry: dict, force: bool = False) -> Path:
    DICT_DIR.mkdir(parents=True, exist_ok=True)
    target = DICT_DIR / entry["file"]
    if target.exists() and not force:
        print(f"  skip {entry['id']:<24} (already present)")
        return target
    raw = download(f"public{entry['url']}")
    words = json.loads(raw.decode("utf-8"))
    target.write_bytes(raw)
    print(f"  got  {entry['id']:<24} {len(words):>5} words  {entry['name']}")
    return target


def main(argv: list[str]) -> int:
    entries = refresh_catalog()
    by_id = {e["id"]: e for e in entries}

    if "--list" in argv:
        for e in entries:
            print(f"{e['id']:<32} {e.get('category',''):<12} {e['length']:>6}  {e['name']}")
        return 0

    wanted = list(by_id) if "--all" in argv else ([a for a in argv if not a.startswith("-")] or DEFAULT_DICTS)
    force = "--force" in argv

    missing = [w for w in wanted if w not in by_id]
    if missing:
        print(f"unknown dictionary ids: {', '.join(missing)}", file=sys.stderr)

    print(f"downloading {len(wanted) - len(missing)} dictionaries into {DICT_DIR}")
    for wid in wanted:
        if wid in by_id:
            try:
                fetch_dict(by_id[wid], force=force)
            except Exception as exc:  # noqa: BLE001 - keep going on a single failure
                print(f"  FAIL {wid}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
