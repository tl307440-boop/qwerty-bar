"""Upstream-style key / hint sounds + Youdao pronunciation.

Sound assets come from RealKai42/qwerty-learner (GPL-3.0):
  assets/sounds/key-sound/Default.wav  — per-keystroke click
  assets/sounds/beep.wav               — wrong key
  assets/sounds/correct.wav            — word finished
"""

from __future__ import annotations

import ctypes
import hashlib
import threading
import urllib.parse
import urllib.request
from pathlib import Path

winmm = ctypes.WinDLL("winmm")
ROOT = Path(__file__).resolve().parent.parent
SOUNDS = ROOT / "assets" / "sounds"
KEY_SOUNDS = SOUNDS / "key-sound"
CACHE = ROOT / "data" / "audio"

_MIRRORS = (
    "https://cdn.jsdelivr.net/gh/RealKai42/qwerty-learner@master/public/sounds",
    "https://raw.githubusercontent.com/RealKai42/qwerty-learner/master/public/sounds",
)

# Mechanical packs available upstream (tplai/kbsim). Default ships locally.
KEY_PACKS = (
    "Default.wav",
    "Cherry MX Blues.mp3",
    "Cherry MX Browns.mp3",
    "Cherry MX Blacks.mp3",
    "Topre.mp3",
    "Holy Pandas.mp3",
    "Buckling Spring.mp3",
)

_lock = threading.Lock()
_alias_seq = 0
_ensured = False


def _mci(command: str) -> None:
    buf = ctypes.create_unicode_buffer(256)
    winmm.mciSendStringW(ctypes.c_wchar_p(command), buf, 256, None)


def _play_file(path: Path, wait: bool = False) -> None:
    """Play wav/mp3. wait=False overlaps better for rapid keystrokes via async WAV."""
    if not path.exists():
        return
    suffix = path.suffix.lower()
    if suffix == ".wav" and not wait:
        try:
            import winsound  # noqa: PLC0415

            # SND_ASYNC = return immediately; overlaps/replaces like Howler interrupt.
            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            return
        except Exception:  # noqa: BLE001
            pass

    global _alias_seq
    with _lock:
        _alias_seq += 1
        alias = f"qwbar{_alias_seq}"
    try:
        kind = "waveaudio" if suffix == ".wav" else "mpegvideo"
        _mci(f'open "{path}" type {kind} alias {alias}')
        _mci(f"play {alias}" + (" wait" if wait else ""))
        if wait:
            _mci(f"close {alias}")
        else:
            # Close after a short delay so the device is released.
            def later():
                try:
                    _mci(f"close {alias}")
                except Exception:  # noqa: BLE001
                    pass

            threading.Timer(1.5, later).start()
    except Exception:  # noqa: BLE001
        try:
            _mci(f"close {alias}")
        except Exception:  # noqa: BLE001
            pass


def _download(rel: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Encode each path segment so "Cherry MX Blues.mp3" works.
    encoded = "/".join(urllib.parse.quote(part) for part in rel.split("/"))
    last = None
    for base in _MIRRORS:
        try:
            req = urllib.request.Request(f"{base}/{encoded}", headers={"User-Agent": "qwerty-bar"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) < 64:
                continue
            dest.write_bytes(data)
            return True
        except Exception as exc:  # noqa: BLE001
            last = exc
    return False


def ensure_sounds() -> None:
    """Make sure the three core clips exist (download from upstream if missing)."""
    global _ensured
    if _ensured:
        return
    needed = {
        "beep.wav": SOUNDS / "beep.wav",
        "correct.wav": SOUNDS / "correct.wav",
        "key-sound/Default.wav": KEY_SOUNDS / "Default.wav",
    }
    for rel, dest in needed.items():
        if not dest.exists():
            _download(rel, dest)
    _ensured = True


def key_pack_path(name: str) -> Path:
    ensure_sounds()
    path = KEY_SOUNDS / name
    if path.exists():
        return path
    # Try on-demand download for optional packs.
    if _download(f"key-sound/{name}", path):
        return path
    return KEY_SOUNDS / "Default.wav"


def list_key_packs() -> list[str]:
    ensure_sounds()
    found = {p.name for p in KEY_SOUNDS.glob("*") if p.suffix.lower() in {".wav", ".mp3"}}
    ordered = [n for n in KEY_PACKS if n in found or n == "Default.wav"]
    for name in sorted(found):
        if name not in ordered:
            ordered.append(name)
    return ordered or ["Default.wav"]


def key(pack: str = "Default.wav") -> None:
    """Per-keystroke click — mirrors upstream playKeySound()."""
    ensure_sounds()
    path = key_pack_path(pack)

    def work():
        try:
            _play_file(path, wait=False)
        except Exception:  # noqa: BLE001
            pass

    # WAV async path is already non-blocking; still offload to keep UI snappy.
    if path.suffix.lower() == ".wav":
        try:
            _play_file(path, wait=False)
            return
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=work, daemon=True).start()


def wrong() -> None:
    """Wrong-key beep — mirrors upstream playBeepSound()."""
    ensure_sounds()
    path = SOUNDS / "beep.wav"

    def work():
        try:
            if path.exists():
                _play_file(path, wait=False)
            else:
                import winsound  # noqa: PLC0415

                winsound.Beep(220, 70)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, daemon=True).start()


def correct() -> None:
    """Word-finished chime — mirrors upstream playHintSound()."""
    ensure_sounds()
    path = SOUNDS / "correct.wav"

    def work():
        try:
            if path.exists():
                _play_file(path, wait=False)
            else:
                import winsound  # noqa: PLC0415

                winsound.Beep(880, 45)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, daemon=True).start()


def blip(kind: str = "ok") -> None:
    """Back-compat wrapper used by chapter rollover etc."""
    if kind == "err":
        wrong()
    elif kind == "ok":
        correct()
    else:
        try:
            import winsound  # noqa: PLC0415

            threading.Thread(target=lambda: winsound.Beep(660, 60), daemon=True).start()
        except Exception:  # noqa: BLE001
            pass


def _cache_path(word: str, accent: str) -> Path:
    digest = hashlib.md5(f"{accent}:{word}".encode("utf-8")).hexdigest()[:16]
    return CACHE / f"{digest}.mp3"


def pronounce(word: str, accent: str = "us") -> None:
    """Fetch (and cache) the Youdao audio clip for a word, then play it."""
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
            _play_file(target, wait=True)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, daemon=True).start()
