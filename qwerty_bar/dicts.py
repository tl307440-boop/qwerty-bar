"""Dictionary catalog access and chapter slicing (mirrors qwerty-learner's model)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DICT_DIR = DATA / "dicts"
CATALOG = DATA / "catalog.json"


@dataclass
class Word:
    name: str
    trans: list[str] = field(default_factory=list)
    usphone: str = ""
    ukphone: str = ""

    def phonetic(self, accent: str = "us") -> str:
        raw = (self.usphone if accent == "us" else self.ukphone) or self.usphone or self.ukphone
        return f"/{raw}/" if raw else ""

    def translation(self) -> str:
        return "; ".join(t.strip() for t in self.trans if t and t.strip())


@dataclass
class DictMeta:
    id: str
    name: str
    file: str
    length: int = 0
    category: str = ""
    description: str = ""
    language: str = "en"
    languageCategory: str = "en"

    @property
    def path(self) -> Path:
        return DICT_DIR / self.file

    @property
    def downloaded(self) -> bool:
        return self.path.exists()


def load_catalog() -> list[DictMeta]:
    try:
        raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - run fetch_dicts.py to create it
        return []
    metas = []
    for item in raw:
        metas.append(
            DictMeta(
                id=item.get("id", ""),
                name=item.get("name", item.get("id", "")),
                file=item.get("file") or item.get("url", "").rsplit("/", 1)[-1],
                length=int(item.get("length", 0) or 0),
                category=item.get("category", ""),
                description=item.get("description", ""),
                language=item.get("language", "en"),
                languageCategory=item.get("languageCategory", "en"),
            )
        )
    return [m for m in metas if m.id and m.file]


def load_words(meta: DictMeta) -> list[Word]:
    raw = json.loads(meta.path.read_text(encoding="utf-8"))
    words = []
    for item in raw:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        trans = item.get("trans") or []
        if isinstance(trans, str):
            trans = [trans]
        words.append(
            Word(
                name=name,
                trans=[str(t) for t in trans],
                usphone=str(item.get("usphone") or ""),
                ukphone=str(item.get("ukphone") or ""),
            )
        )
    return words


def download_dict(meta: DictMeta, on_done=None) -> threading.Thread:
    """Fetch a dictionary in the background; on_done(ok, message) runs on the worker thread."""

    def work():
        try:
            import sys

            sys.path.insert(0, str(ROOT))
            from fetch_dicts import download  # noqa: PLC0415 - optional at runtime

            DICT_DIR.mkdir(parents=True, exist_ok=True)
            raw = download(f"public/dicts/{meta.file}")
            json.loads(raw.decode("utf-8"))
            meta.path.write_bytes(raw)
            if on_done:
                on_done(True, meta.name)
        except Exception as exc:  # noqa: BLE001
            if on_done:
                on_done(False, str(exc))

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return thread


class Session:
    """A dictionary split into fixed-size chapters, with a cursor into the current one."""

    def __init__(self, meta: DictMeta, words: list[Word], chapter_size: int = 20):
        self.meta = meta
        self.words = words
        self.chapter_size = max(1, chapter_size)
        self.chapter = 0
        self.index = 0

    @property
    def chapter_count(self) -> int:
        return max(1, -(-len(self.words) // self.chapter_size))

    def chapter_words(self) -> list[Word]:
        start = self.chapter * self.chapter_size
        return self.words[start : start + self.chapter_size]

    @property
    def chapter_len(self) -> int:
        return len(self.chapter_words()) or 1

    def current(self) -> Word | None:
        chapter = self.chapter_words()
        if not chapter:
            return None
        self.index = min(self.index, len(chapter) - 1)
        return chapter[self.index]

    def seek(self, chapter: int, index: int = 0) -> None:
        self.chapter = max(0, min(chapter, self.chapter_count - 1))
        self.index = max(0, min(index, self.chapter_len - 1))

    def advance(self, step: int = 1) -> bool:
        """Move by `step` words, rolling over chapter boundaries. True if the chapter changed."""
        self.index += step
        rolled = False
        while self.index >= self.chapter_len:
            self.index -= self.chapter_len
            self.chapter = (self.chapter + 1) % self.chapter_count
            rolled = True
        while self.index < 0:
            self.chapter = (self.chapter - 1) % self.chapter_count
            self.index += self.chapter_len
            rolled = True
        return rolled
