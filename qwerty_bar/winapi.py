"""Win32 glue: DPI awareness, taskbar geometry, borderless tool windows, global hotkeys."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
imm32 = ctypes.WinDLL("imm32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

ABM_GETTASKBARPOS = 0x00000005
ABE_LEFT, ABE_TOP, ABE_RIGHT, ABE_BOTTOM = 0, 1, 2, 3

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", wintypes.RECT),
        ("lParam", wintypes.LPARAM),
    ]


def enable_dpi_awareness() -> None:
    """Per-monitor-v2 keeps the bar crisp and correctly sized on scaled displays."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        try:
            user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def hwnd_of(tk_window) -> int:
    """Top-level HWND for a Tk window, with or without a native frame."""
    tk_window.update_idletasks()
    hwnd = int(tk_window.winfo_id())
    parent = user32.GetParent(wintypes.HWND(hwnd))
    return int(parent) if parent else hwnd


def make_tool_window(hwnd: int, no_activate: bool = False) -> None:
    """Hide from Alt-Tab and the taskbar button list."""
    style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
    style |= WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    if no_activate:
        style |= WS_EX_NOACTIVATE
    else:
        style &= ~WS_EX_NOACTIVATE
    user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)


ENUM_CHILD = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def disable_ime(hwnd: int) -> None:
    """Detach the IME from the bar and its children.

    Without this, a Chinese IME eats every keystroke into a pinyin composition
    window instead of letting the raw latin letters reach the typing engine.
    """
    handles = [hwnd]

    @ENUM_CHILD
    def collect(child, _lparam):
        handles.append(int(child))
        return True

    user32.EnumChildWindows(wintypes.HWND(hwnd), collect, 0)
    for handle in handles:
        try:
            imm32.ImmAssociateContext(wintypes.HWND(handle), None)
        except Exception:  # noqa: BLE001
            pass


def assert_topmost(hwnd: int) -> None:
    """Re-raise above the taskbar; the shell steals the top slot back periodically."""
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        wintypes.HWND(HWND_TOPMOST),
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


def taskbar_rect() -> tuple[int, int, int, int, int]:
    """Return (left, top, right, bottom, edge) of the primary taskbar."""
    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(APPBARDATA)
    if shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(data)):
        r = data.rc
        return r.left, r.top, r.right, r.bottom, int(data.uEdge)

    # Fallback: infer the taskbar strip from the work-area / screen difference.
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    work = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)
    return 0, work.bottom, sw, sh, ABE_BOTTOM


def work_area() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


def foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow())


def focus_window(hwnd: int) -> None:
    """Steal focus reliably by riding the foreground window's input queue."""
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return
    cur = ctypes.windll.kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None)
    attached = bool(other and other != cur and user32.AttachThreadInput(other, cur, True))
    try:
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
        user32.SetFocus(wintypes.HWND(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(other, cur, False)


class HotkeyListener(threading.Thread):
    """Registers global hotkeys on a private thread with its own message pump."""

    def __init__(self, bindings: dict[int, tuple[int, int, Callable[[], None]]]):
        super().__init__(daemon=True, name="qwerty-hotkeys")
        self.bindings = bindings
        self._tid = 0

    def run(self) -> None:
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        registered = []
        for hid, (mods, vk, _) in self.bindings.items():
            if user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk):
                registered.append(hid)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                binding = self.bindings.get(int(msg.wParam))
                if binding:
                    try:
                        binding[2]()
                    except Exception:  # noqa: BLE001 - never kill the pump
                        pass
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        for hid in registered:
            user32.UnregisterHotKey(None, hid)


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """Parse strings like 'ctrl+alt+q' into (modifiers, virtual-key)."""
    if not text:
        return None
    mods, vk = 0, None
    table = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
    specials = {
        "space": 0x20, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "enter": 0x0D,
        "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
        "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
    }
    for part in (p.strip().lower() for p in text.split("+")):
        if part in table:
            mods |= table[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part in specials:
            vk = specials[part]
        elif part.startswith("f") and part[1:].isdigit():
            vk = 0x70 + int(part[1:]) - 1
    return (mods, vk) if vk else None
