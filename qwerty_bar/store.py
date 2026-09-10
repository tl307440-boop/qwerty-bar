"""Persistent settings and per-dictionary progress."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE_FILE = DATA / "state.json"

DEFAULTS: dict[str, Any] = {
    "dict_id": "ielts",
    "chapter": 0,
    "index": 0,
    "chapter_size": 20,
    "show_translation": True,
    "show_phonetic": False,
    "dictation": False,          # hide the word, type it from memory
    "loop_word": False,          # stay on the same word until toggled off
    "sound": True,               # per-key click + wrong/correct hint sounds
    "key_sound": "Default.wav",  # file under assets/sounds/key-sound/
    "pronounce": True,           # speak each word as soon as it appears
    "accent": "us",              # us | uk
    "theme": "auto",             # auto | dark | light
    "font_size": 11,
    "max_width": 900,
    "dock": "taskbar",           # taskbar | above | free
    "align": "left",             # left | center | right (taskbar / above modes)
    "offset_x": 16,
    "free_x": 200,
    "free_y": 200,
    "hotkey_toggle": "ctrl+alt+q",
    "hotkey_boss": "ctrl+alt+h",
    "opacity": 1.0,
    "progress": {},              # dict_id -> {"chapter": int, "index": int}
    "stats": {"typed": 0, "errors": 0, "words": 0},
}


class Store:
    def __init__(self) -> None:
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - missing or corrupt state falls back to defaults
            return
        for key, value in saved.items():
            if key in DEFAULTS:
                self.data[key] = value

    def save(self) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STATE_FILE)

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def toggle(self, key: str) -> bool:
        self.data[key] = not self.data.get(key, False)
        return self.data[key]

    def remember_progress(self, dict_id: str, chapter: int, index: int) -> None:
        self.data.setdefault("progress", {})[dict_id] = {"chapter": chapter, "index": index}

    def recall_progress(self, dict_id: str) -> tuple[int, int]:
        entry = self.data.get("progress", {}).get(dict_id) or {}
        return int(entry.get("chapter", 0)), int(entry.get("index", 0))

    def bump(self, field: str, amount: int = 1) -> None:
        stats = self.data.setdefault("stats", {"typed": 0, "errors": 0, "words": 0})
        stats[field] = stats.get(field, 0) + amount
