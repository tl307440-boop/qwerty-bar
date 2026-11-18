"""Dictionary catalog access and chapter slicing (mirrors qwerty-learner's model)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .paths import APP_ROOT, CUSTOM_DIR, DATA, frozen

DICT_DIR = DATA / "dicts"
CATALOG = DATA / "catalog.json"
CUSTOM_CATALOG = CUSTOM_DIR / "catalog.json"


@dataclass
class Word:
    name: str
    trans: list[str] = field(default_factory=list)
    usphone: str = ""
    ukphone: str = ""
    notes: list[str] = field(default_factory=list)  # roots, collocations, ... shown after the meaning
    group: str = ""    # chapter title for dictionaries that ship their own chapters, e.g. "List 1 政治"
    theme: str = ""    # optional parent heading of the chapter, e.g. "主题一 财政法律"

    def phonetic(self, accent: str = "us") -> str:
        raw = (self.usphone if accent == "us" else self.ukphone) or self.usphone or self.ukphone
        return f"/{raw}/" if raw else ""

    def translation(self) -> str:
        meaning = "; ".join(t.strip() for t in self.trans if t and t.strip())
        extra = "  ".join(f"\u25c7 {n}" for n in self.notes if n)
        return f"{meaning}  {extra}" if meaning and extra else (meaning or extra)


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
    custom: bool = False  # bundled with the app, lives in custom_dicts/ instead of data/dicts/

    @property
    def path(self) -> Path:
        return (CUSTOM_DIR if self.custom else DICT_DIR) / self.file

    @property
    def downloaded(self) -> bool:
        return self.path.exists()


def _read_catalog(path: Path, custom: bool) -> list[DictMeta]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
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
                custom=custom,
            )
        )
    return [m for m in metas if m.id and m.file]


def load_catalog() -> list[DictMeta]:
    """Upstream catalog plus the bundled custom dictionaries (placed right after CET-6)."""
    metas = _read_catalog(CATALOG, custom=False)
    custom = _read_catalog(CUSTOM_CATALOG, custom=True)
    if not custom:
        return metas
    ids = {m.id for m in custom}
    metas = [m for m in metas if m.id not in ids]
    at = next((i + 1 for i, m in enumerate(metas) if m.id == "cet6"), len(metas))
    return metas[:at] + custom + metas[at:]


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
                notes=[str(n) for n in (item.get("notes") or [])],
                group=str(item.get("chapter") or ""),
                theme=str(item.get("theme") or ""),
            )
        )
    return words


def download_dict(meta: DictMeta, on_done=None) -> threading.Thread:
    """Fetch a dictionary in the background; on_done(ok, message) runs on the worker thread."""

    def work():
        try:
            import sys

            if not frozen():
                sys.path.insert(0, str(APP_ROOT))
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
    """A dictionary split into chapters, with a cursor into the current one.

    Words that carry a ``chapter`` title (custom dictionaries) are grouped by it, in order of
    appearance. Everything else is cut into fixed-size chapters, as qwerty-learner does.
    """

    def __init__(self, meta: DictMeta, words: list[Word], chapter_size: int = 20):
        self.meta = meta
        self.words = words
        self.chapter_size = max(1, chapter_size)
        self.chapter = 0
        self.index = 0
        self._chapters: list[list[Word]] = self._split()

    def _split(self) -> list[list[Word]]:
        if self.words and all(w.group for w in self.words):
            groups: dict[str, list[Word]] = {}
            for w in self.words:
                groups.setdefault(w.group, []).append(w)
            return list(groups.values())
        size = self.chapter_size
        return [self.words[i : i + size] for i in range(0, len(self.words), size)] or [[]]

    @property
    def titled(self) -> bool:
        """True when chapters have names of their own (instead of plain numbers)."""
        return bool(self.words) and bool(self.words[0].group)

    @property
    def chapter_count(self) -> int:
        return max(1, len(self._chapters))

    def chapter_title(self, chapter: int | None = None) -> str:
        i = self.chapter if chapter is None else chapter
        if self.titled and 0 <= i < len(self._chapters) and self._chapters[i]:
            return self._chapters[i][0].group
        return f"chp.{i + 1}"

    def chapter_theme(self, chapter: int) -> str:
        if self.titled and 0 <= chapter < len(self._chapters) and self._chapters[chapter]:
            return self._chapters[chapter][0].theme
        return ""

    def chapter_words(self) -> list[Word]:
        return self._chapters[self.chapter] if self.chapter < len(self._chapters) else []

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

    def advance(self, step: int = 1, loop_chapter: bool = False) -> bool:
        """Move by `step` words, rolling over chapter boundaries. True if the chapter changed."""
        if loop_chapter:
            n = max(1, self.chapter_len)
            self.index = (self.index + step) % n
            return False
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
