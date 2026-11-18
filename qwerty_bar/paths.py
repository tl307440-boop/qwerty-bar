"""Resolve bundled (read-only) files vs writable user data.

From source, both live in the repo root. After PyInstaller freeze, resources
sit inside the bundle and user data sits next to QwertyBar.exe so a zip
folder is portable — classmates can extract anywhere and double-click.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_root() -> Path:
    if frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


RESOURCE_ROOT = resource_root()
APP_ROOT = app_root()
DATA = APP_ROOT / "data"
# Dictionaries that ship with this app (not downloaded from upstream): read-only, bundled.
CUSTOM_DIR = RESOURCE_ROOT / "custom_dicts"


def ensure_layout() -> None:
    """Create the writable data folder and seed it from the bundle on first run."""
    DATA.mkdir(parents=True, exist_ok=True)
    dest_dicts = DATA / "dicts"
    dest_dicts.mkdir(parents=True, exist_ok=True)

    src_data = RESOURCE_ROOT / "data"
    if not src_data.exists():
        return
    try:
        if src_data.resolve() == DATA.resolve():
            return
    except OSError:
        pass

    src_catalog = src_data / "catalog.json"
    dest_catalog = DATA / "catalog.json"
    if src_catalog.exists() and not dest_catalog.exists():
        shutil.copy2(src_catalog, dest_catalog)

    src_dicts = src_data / "dicts"
    if not src_dicts.exists():
        return
    for path in src_dicts.glob("*.json"):
        target = dest_dicts / path.name
        if not target.exists():
            shutil.copy2(path, target)
