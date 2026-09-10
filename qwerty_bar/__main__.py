"""Entry point: enforce a single instance, then run the bar."""

from __future__ import annotations

import ctypes
import sys

from . import winapi
from .bar import SHOW_FLAG, WordBar

MUTEX_NAME = "Global\\QwertyBarSingleInstance"
ERROR_ALREADY_EXISTS = 183


def claim_single_instance() -> bool:
    """False if another instance owns the mutex — we just ask it to show itself."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        SHOW_FLAG.parent.mkdir(parents=True, exist_ok=True)
        SHOW_FLAG.write_text("show", encoding="utf-8")
        return False
    return True


def main() -> int:
    if not claim_single_instance():
        return 0
    winapi.enable_dpi_awareness()
    WordBar().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
