"""Word pronunciation (Youdao) plus lightweight success/error blips."""

from __future__ import annotations

import ctypes
import hashlib
import threading
import urllib.parse
import urllib.request
from pathlib import Path

winmm = ctypes.WinDLL("winmm")
CACHE = Path(__file__).resolve().parent.parent / "data" / "audio"
_lock = threading.Lock()
_alias_seq = 0


def _mci(command: str) -> None:
    buf = ctypes.create_unicode_buffer(256)
    winmm.mciSendStringW(ctypes.c_wchar_p(command), buf, 256, None)


def _play_file(path: Path) -> None:
    global _alias_seq
    with _lock:
        _alias_seq += 1
        alias = f"qwbar{_alias_seq}"
    _mci(f'open "{path}" type mpegvideo alias {alias}')
    _mci(f"play {alias} wait")
    _mci(f"close {alias}")


def _cache_path(word: str, accent: str) -> Path:
    digest = hashlib.md5(f"{accent}:{word}".encode("utf-8")).hexdigest()[:16]
    return CACHE / f"{digest}.mp3"


def pronounce(word: str, accent: str = "us") -> None:
    """Fetch (and cache) the Youdao audio clip for a word, then play it. Non-blocking."""
    if not word:
        return

    def work():
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            target = _cache_path(word, accent)
            if not target.exists():
                query = urllib.parse.urlencode({"audio": word, "type": 2 if accent == "us" else 1})
                req = urllib.request.Request(
                    f"https://dict.youdao.com/dictvoice?{query}",
                    headers={"User-Agent": "Mozilla/5.0 qwerty-bar"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    payload = resp.read()
                if len(payload) < 512:
                    return
                target.write_bytes(payload)
            _play_file(target)
        except Exception:  # noqa: BLE001 - audio is best-effort
            pass

    threading.Thread(target=work, daemon=True).start()


def blip(kind: str = "ok") -> None:
    """Short non-blocking feedback tone."""

    def work():
        try:
            import winsound  # noqa: PLC0415 - Windows only

            if kind == "ok":
                winsound.Beep(880, 45)
            elif kind == "chapter":
                winsound.Beep(660, 60)
                winsound.Beep(990, 80)
            else:
                winsound.Beep(220, 70)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, daemon=True).start()
