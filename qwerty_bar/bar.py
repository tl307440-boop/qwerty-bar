"""The taskbar word bar: rendering, typing engine and interaction."""

from __future__ import annotations

import queue
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

from . import audio, winapi
from .dicts import DictMeta, Session, download_dict, load_catalog, load_words
from .store import DATA, Store

DARK = {
    "bg": "#1c1c1c",
    "meta": "#8a8a8a",
    "progress": "#6f9ad6",
    "done": "#4ec994",
    "pending": "#d6d6d6",
    "ghost": "#5a5a5a",
    "error": "#f2545b",
    "trans": "#9b9b9b",
    "phonetic": "#7f7f7f",
    "button": "#8a8a8a",
    "button_hot": "#ffffff",
    "focus_on": "#4ec994",
    "focus_off": "#3a3a3a",
    "rule": "#2e2e2e",
}

LIGHT = {
    "bg": "#f3f3f3",
    "meta": "#5f5f5f",
    "progress": "#2f6db3",
    "done": "#137a4d",
    "pending": "#1f1f1f",
    "ghost": "#b0b0b0",
    "error": "#c42b1c",
    "trans": "#4a4a4a",
    "phonetic": "#6b6b6b",
    "button": "#5f5f5f",
    "button_hot": "#000000",
    "focus_on": "#137a4d",
    "focus_off": "#cfcfcf",
    "rule": "#dcdcdc",
}

PAD = 10
GAP = 12
SHOW_FLAG = DATA / "show.flag"

ICON_SAY = "\u266a"
ICON_PREV = "\u2039"
ICON_NEXT = "\u203a"
ICON_MENU = "\u22ee"
MARK_ON = "\u25cf"      # filled circle for the active radio choice
MARK_TICK = "\u2713"
MARK_DOWN = "\u2913"    # not downloaded yet
ELLIPSIS = "\u2026"


def system_uses_light_theme() -> bool:
    import winreg

    try:
        key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            return bool(winreg.QueryValueEx(handle, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def palette(mode: str) -> dict:
    if mode == "auto":
        mode = "light" if system_uses_light_theme() else "dark"
    return dict(LIGHT if mode == "light" else DARK)


class WordBar:
    def __init__(self) -> None:
        self.store = Store()
        self.theme = palette(self.store["theme"])
        self.catalog = load_catalog()
        self.by_id = {m.id: m for m in self.catalog}
        self.events: queue.Queue = queue.Queue()

        self.typed = ""
        self.error_at = -1
        self.hidden = False
        self.focused = False
        self._drag = None
        self._hwnd = 0
        self._advancing = False

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Qwerty Bar")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.theme["bg"])

        size = int(self.store["font_size"])
        self.f_word = tkfont.Font(family="Consolas", size=size + 1, weight="bold")
        self.f_meta = tkfont.Font(family="Microsoft YaHei UI", size=size - 2)
        self.f_text = tkfont.Font(family="Microsoft YaHei UI", size=size - 1)
        self.f_icon = tkfont.Font(family="Segoe UI Symbol", size=size)

        self.height = self._bar_height()
        self.canvas = tk.Canvas(
            self.root, bg=self.theme["bg"], highlightthickness=0, bd=0, height=self.height, width=600
        )
        self.canvas.pack(fill="both", expand=True)

        self.session = self._open_dictionary(self.store["dict_id"], restore=True)
        self._bind()
        self._boot()

    # ------------------------------------------------------------------ setup

    def _bar_height(self) -> int:
        return max(self.f_word.metrics("linespace"), self.f_text.metrics("linespace")) + 10

    def _boot(self) -> None:
        self.root.deiconify()
        self.root.update_idletasks()
        self._hwnd = winapi.hwnd_of(self.root)
        try:
            # Set alpha first: Tk rewrites the whole ex-style here and would
            # otherwise wipe the tool-window bit we apply below.
            self.root.attributes("-alpha", float(self.store["opacity"]))
        except Exception:  # noqa: BLE001
            pass
        self._apply_window_styles()
        self.render()
        self._install_hotkeys()
        self._tick()
        self._poll_events()
        # Defer so the window is on screen before Youdao audio starts.
        self.root.after(200, self._announce_current)

    def _bind(self) -> None:
        c = self.canvas
        c.bind("<Button-1>", self._on_click)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_drop)
        c.bind("<Button-3>", self._on_menu)
        c.bind("<MouseWheel>", self._on_wheel)
        self.root.bind("<Key>", self._on_key)
        self.root.bind("<FocusIn>", lambda _e: self._set_focus(True))
        self.root.bind("<FocusOut>", lambda _e: self._set_focus(False))

    def _apply_window_styles(self) -> None:
        winapi.make_tool_window(self._hwnd)
        winapi.disable_ime(self._hwnd)

    def _install_hotkeys(self) -> None:
        bindings = {}
        toggle = winapi.parse_hotkey(self.store["hotkey_toggle"])
        boss = winapi.parse_hotkey(self.store["hotkey_boss"])
        if toggle:
            bindings[1] = (*toggle, lambda: self.events.put("toggle"))
        if boss:
            bindings[2] = (*boss, lambda: self.events.put("boss"))
        if bindings:
            winapi.HotkeyListener(bindings).start()

    # ------------------------------------------------------------- dictionary

    def _open_dictionary(self, dict_id: str, restore: bool = False) -> Session:
        meta = self.by_id.get(dict_id)
        if meta is None or not meta.downloaded:
            meta = next((m for m in self.catalog if m.downloaded), None)
        if meta is None:
            meta = DictMeta(id="empty", name="no dict", file="")
            session = Session(meta, [], int(self.store["chapter_size"]))
        else:
            session = Session(meta, load_words(meta), int(self.store["chapter_size"]))

        if restore:
            chapter, index = self.store.recall_progress(meta.id)
            session.seek(chapter, index)
        self.store["dict_id"] = meta.id
        self.typed, self.error_at = "", -1
        return session

    def switch_dictionary(self, dict_id: str) -> None:
        meta = self.by_id.get(dict_id)
        if meta is None:
            return
        if not meta.downloaded:
            self._flash(f"正在下载 {meta.name} ...")
            download_dict(meta, lambda ok, msg: self.events.put(("downloaded", dict_id, ok, msg)))
            return
        self._save_progress()
        self.session = self._open_dictionary(dict_id, restore=True)
        self._persist()
        self.render()
        self._announce_current()

    def _save_progress(self) -> None:
        self.store.remember_progress(self.session.meta.id, self.session.chapter, self.session.index)
        self.store["chapter"] = self.session.chapter
        self.store["index"] = self.session.index

    def _persist(self) -> None:
        self._save_progress()
        self.store.save()

    # ---------------------------------------------------------------- drawing

    def render(self) -> None:
        c = self.canvas
        c.delete("all")
        mid = self.height // 2
        x = PAD + 4

        # Focus stripe: coloured means keystrokes land here.
        c.create_rectangle(
            0, 0, 3, self.height, width=0,
            fill=self.theme["focus_on"] if self.focused else self.theme["focus_off"],
        )

        session = self.session
        word = session.current()

        x = self._put(x, mid, f"{session.meta.name} chp.{session.chapter + 1}", self.f_meta, self.theme["meta"], "dict")
        x += GAP
        x = self._put(
            x, mid, f"{session.index + 1}/{session.chapter_len}", self.f_meta, self.theme["progress"], "chapter"
        )
        x += GAP

        if word is None:
            self._put(x, mid, "没有可用词库，请先运行 fetch_dicts.py", self.f_text, self.theme["error"])
            self._resize(x + 300)
            return

        x = self._draw_word(x, mid, word.name)
        x += GAP

        if self.store["show_phonetic"]:
            phonetic = word.phonetic(self.store["accent"])
            if phonetic:
                x = self._put(x, mid, phonetic, self.f_meta, self.theme["phonetic"])
                x += GAP

        if self.store["show_translation"]:
            avail = int(self.store["max_width"]) - x - self._controls_width() - PAD * 2
            text = self._truncate(word.translation(), self.f_text, max(avail, 60))
            if text:
                x = self._put(x, mid, text, self.f_text, self.theme["trans"], "trans")
                x += GAP

        x = self._draw_controls(x, mid)
        self._resize(x + PAD)
        self._draw_chapter_rule()

    def _draw_word(self, x: int, mid: int, name: str) -> int:
        """Typed prefix in green (red on a miss); the rest dim, or masked in dictation mode."""
        n = len(self.typed)
        done, rest = name[:n], name[n:]
        if done:
            colour = self.theme["error"] if self.error_at >= 0 else self.theme["done"]
            x = self._put(x, mid, done, self.f_word, colour, "word")
        if rest:
            masked = "".join("_" if ch != " " else " " for ch in rest) if self.store["dictation"] else rest
            colour = self.theme["ghost"] if self.store["dictation"] else self.theme["pending"]
            x = self._put(x, mid, masked, self.f_word, colour, "word")
        return x

    def _controls_width(self) -> int:
        return sum(self.f_icon.measure(t) + 10 for t in (ICON_SAY, ICON_PREV, ICON_NEXT, ICON_MENU))

    def _draw_controls(self, x: int, mid: int) -> int:
        for glyph, tag, action in (
            (ICON_SAY, "say", self._pronounce),
            (ICON_PREV, "prev", lambda: self.step(-1)),
            (ICON_NEXT, "next", lambda: self.step(1)),
            (ICON_MENU, "menu", lambda: self._on_menu(None)),
        ):
            item = self.canvas.create_text(
                x + 5, mid, text=glyph, font=self.f_icon, fill=self.theme["button"], anchor="w", tags=("btn", tag)
            )
            self.canvas.tag_bind(item, "<Button-1>", lambda _e, fn=action: self._button(fn))
            self.canvas.tag_bind(
                item, "<Enter>", lambda _e, i=item: self.canvas.itemconfig(i, fill=self.theme["button_hot"])
            )
            self.canvas.tag_bind(
                item, "<Leave>", lambda _e, i=item: self.canvas.itemconfig(i, fill=self.theme["button"])
            )
            x += self.f_icon.measure(glyph) + 10
        return x

    def _draw_chapter_rule(self) -> None:
        """Hairline along the bottom showing how far through the chapter you are."""
        width = self.canvas.winfo_reqwidth()
        done = self.session.index / max(1, self.session.chapter_len)
        y = self.height - 2
        self.canvas.create_line(0, y, width, y, fill=self.theme["rule"], width=2)
        if done > 0:
            self.canvas.create_line(0, y, int(width * done), y, fill=self.theme["progress"], width=2)

    def _put(self, x: int, mid: int, text: str, font, fill: str, tag: str | None = None) -> int:
        tags = ("seg", tag) if tag else ("seg",)
        self.canvas.create_text(x, mid, text=text, font=font, fill=fill, anchor="w", tags=tags)
        return x + font.measure(text)

    def _truncate(self, text: str, font, avail: int) -> str:
        if not text or font.measure(text) <= avail:
            return text
        tail = font.measure(ELLIPSIS)
        out = ""
        for ch in text:
            if font.measure(out + ch) + tail > avail:
                break
            out += ch
        return out + ELLIPSIS

    def _resize(self, width: int) -> None:
        width = max(240, min(int(width), int(self.store["max_width"])))
        self.canvas.configure(width=width, height=self.height)
        self.reposition(width)

    def reposition(self, width: int | None = None) -> None:
        width = width or self.canvas.winfo_reqwidth()
        dock, align = self.store["dock"], self.store["align"]
        off = int(self.store["offset_x"])

        if dock == "free":
            x, y = int(self.store["free_x"]), int(self.store["free_y"])
        else:
            left, top, right, bottom, edge = winapi.taskbar_rect()
            if dock == "taskbar" and edge in (winapi.ABE_TOP, winapi.ABE_BOTTOM):
                y = top + max(0, (bottom - top - self.height) // 2)
                strip_l, strip_r = left, right
            else:
                wl, _wt, wr, wb = winapi.work_area()
                y = wb - self.height - 6
                strip_l, strip_r = wl, wr
            if align == "right":
                x = strip_r - width - off
            elif align == "center":
                x = (strip_l + strip_r) // 2 - width // 2
            else:
                x = strip_l + off
        self.root.geometry(f"{width}x{self.height}+{int(x)}+{int(y)}")

    # ------------------------------------------------------------ typing core

    def _on_key(self, event: tk.Event) -> str | None:
        key = event.keysym
        if key == "Escape":
            self.hide()
            return "break"
        if key == "BackSpace":
            self.typed, self.error_at = self.typed[:-1], -1
            self.render()
            return "break"
        if key in ("Right", "Down"):
            self.step(1)
            return "break"
        if key in ("Left", "Up"):
            self.step(-1)
            return "break"
        if key == "Return":
            self._pronounce()
            return "break"
        if key == "Tab":
            self.store.toggle("dictation")
            self.store.save()
            self.render()
            return "break"

        char = event.char
        if not char or len(char) != 1 or ord(char) < 32:
            return None
        self._type(char)
        return "break"

    def _type(self, char: str) -> None:
        word = self.session.current()
        if word is None or self._advancing:
            return
        expected = word.name[len(self.typed) : len(self.typed) + 1]
        self.store.bump("typed")

        if expected and char.lower() == expected.lower():
            self.typed += expected
            self.error_at = -1
            if len(self.typed) >= len(word.name):
                self._complete(word)
                return
            self.render()
            return

        # Wrong key: flash the word red, then make the user retype it from the top.
        self.store.bump("errors")
        self.error_at = len(self.typed)
        self.typed = word.name[: self.error_at + 1]
        self.render()
        if self.store["sound"]:
            audio.blip("err")
        self.root.after(220, self._reset_word)

    def _reset_word(self) -> None:
        self.typed, self.error_at = "", -1
        self.render()

    def _complete(self, word) -> None:
        # Pronunciation belongs to the *next* word's transaction (on appear),
        # not after we have already jumped away from this one.
        self._advancing = True
        self.render()
        self.store.bump("words")
        if self.store["sound"]:
            audio.blip("ok")

        def go():
            self._advancing = False
            if self.store["loop_word"]:
                self._reset_word()
                self._announce_current()
            else:
                self.step(1, silent=True)

        self.root.after(180, go)

    def step(self, delta: int, silent: bool = False) -> None:
        rolled = self.session.advance(delta)
        self.typed, self.error_at = "", -1
        if rolled and not silent and self.store["sound"]:
            audio.blip("chapter")
        self._persist()
        self.render()
        self._announce_current()

    def jump_chapter(self, chapter: int) -> None:
        self.session.seek(chapter, 0)
        self.typed, self.error_at = "", -1
        self._persist()
        self.render()
        self._announce_current()

    def _announce_current(self) -> None:
        """Speak the word that just became current — start of its typing transaction."""
        if not self.store["pronounce"]:
            return
        word = self.session.current()
        if word:
            audio.pronounce(word.name, self.store["accent"])

    def _pronounce(self) -> None:
        word = self.session.current()
        if word:
            audio.pronounce(word.name, self.store["accent"])

    # ------------------------------------------------------------ interaction

    def _button(self, fn) -> None:
        self._activate()
        fn()

    def _on_click(self, event: tk.Event) -> None:
        if "btn" in self.canvas.gettags("current"):
            return
        self._activate()
        tags = self.canvas.gettags("current")
        if "dict" in tags:
            self._menu_dictionaries().tk_popup(event.x_root, event.y_root)
            return
        if "chapter" in tags:
            self._menu_chapters().tk_popup(event.x_root, event.y_root)
            return
        self._drag = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag:
            return
        ox, oy, wx, wy = self._drag
        dx, dy = event.x_root - ox, event.y_root - oy
        if abs(dx) + abs(dy) < 3:
            return
        if self.store["dock"] == "free":
            self.store["free_x"], self.store["free_y"] = wx + dx, wy + dy
        else:
            shift = -dx if self.store["align"] == "right" else dx
            self.store["offset_x"] = max(0, int(self.store["offset_x"]) + shift)
            self._drag = (event.x_root, event.y_root, wx, wy)
        self.reposition()

    def _on_drop(self, _event: tk.Event) -> None:
        if self._drag:
            self._drag = None
            self.store.save()

    def _on_wheel(self, event: tk.Event) -> None:
        self.step(-1 if event.delta > 0 else 1)

    def _activate(self) -> None:
        try:
            winapi.focus_window(self._hwnd)
            winapi.disable_ime(self._hwnd)
        except Exception:  # noqa: BLE001
            pass
        self.root.focus_force()
        self._set_focus(True)

    def _set_focus(self, value: bool) -> None:
        if value != self.focused:
            self.focused = value
            self.render()

    def _flash(self, message: str, ms: int = 1600) -> None:
        self.canvas.delete("all")
        self._put(PAD + 4, self.height // 2, message, self.f_text, self.theme["progress"])
        self.root.after(ms, self.render)

    # ------------------------------------------------------------------ menus

    def _new_menu(self) -> tk.Menu:
        return tk.Menu(self.root, tearoff=0, font=("Microsoft YaHei UI", 9))

    def _radio(self, menu: tk.Menu, active: bool, label: str, command) -> None:
        menu.add_command(label=f"{MARK_ON if active else '   '} {label}", command=command)

    def _menu_dictionaries(self) -> tk.Menu:
        menu = self._new_menu()
        for i, meta in enumerate(m for m in self.catalog if m.downloaded):
            if i and i % 24 == 0:
                menu.entryconfigure(menu.index("end"), columnbreak=1)
            self._radio(
                menu,
                meta.id == self.session.meta.id,
                f"{meta.name}  ({meta.length})",
                lambda mid=meta.id: self.switch_dictionary(mid),
            )
        menu.add_separator()

        more = self._new_menu()
        categories: dict[str, list[DictMeta]] = {}
        for meta in self.catalog:
            categories.setdefault(meta.category or "其他", []).append(meta)
        for category, metas in categories.items():
            sub = self._new_menu()
            for i, meta in enumerate(metas):
                if i and i % 25 == 0:
                    sub.entryconfigure(sub.index("end"), columnbreak=1)
                mark = MARK_TICK if meta.downloaded else MARK_DOWN
                sub.add_command(
                    label=f"{mark} {meta.name}  ({meta.length})",
                    command=lambda mid=meta.id: self.switch_dictionary(mid),
                )
            more.add_cascade(label=f"{category}  ({len(metas)})", menu=sub)
        menu.add_cascade(label=f"全部词库 {ELLIPSIS}", menu=more)
        return menu

    def _menu_chapters(self) -> tk.Menu:
        menu = self._new_menu()
        for i in range(self.session.chapter_count):
            if i and i % 25 == 0:
                menu.entryconfigure(menu.index("end"), columnbreak=1)
            self._radio(menu, i == self.session.chapter, f"第 {i + 1} 章", lambda c=i: self.jump_chapter(c))
        return menu

    def _on_menu(self, event) -> None:
        menu = self._new_menu()
        store = self.store

        menu.add_cascade(label=f"词库：{self.session.meta.name}", menu=self._menu_dictionaries())
        menu.add_cascade(label=f"章节：第 {self.session.chapter + 1} 章", menu=self._menu_chapters())
        menu.add_separator()

        def flag(key: str, label: str) -> None:
            menu.add_command(
                label=f"{MARK_TICK if store[key] else '   '} {label}",
                command=lambda: (store.toggle(key), store.save(), self.render()),
            )

        flag("show_translation", "显示释义")
        flag("show_phonetic", "显示音标")
        flag("dictation", "默写模式（隐藏单词，Tab 切换）")
        flag("loop_word", "单词循环")
        flag("pronounce", "新词出现时自动发音")
        flag("sound", "按键提示音")

        accent = self._new_menu()
        for code, label in (("us", "美音"), ("uk", "英音")):
            self._radio(
                accent, store["accent"] == code, label,
                lambda c=code: (store.__setitem__("accent", c), store.save(), self.render()),
            )
        menu.add_cascade(label="发音口音", menu=accent)
        menu.add_separator()

        place = self._new_menu()
        for code, label in (("taskbar", "贴在任务栏上"), ("above", "任务栏上方"), ("free", "自由拖动")):
            self._radio(place, store["dock"] == code, label, lambda c=code: self._set_dock(c))
        place.add_separator()
        for code, label in (("left", "靠左"), ("center", "居中"), ("right", "靠右")):
            self._radio(
                place, store["align"] == code, label,
                lambda c=code: (store.__setitem__("align", c), store.save(), self.reposition()),
            )
        menu.add_cascade(label="位置", menu=place)

        look = self._new_menu()
        for code, label in (("auto", "跟随系统"), ("dark", "深色"), ("light", "浅色")):
            self._radio(look, store["theme"] == code, label, lambda c=code: self._set_theme(c))
        look.add_separator()
        for n in (9, 10, 11, 12, 13, 14):
            self._radio(look, int(store["font_size"]) == n, f"字号 {n}", lambda n=n: self._set_font_size(n))
        look.add_separator()
        for n in (600, 750, 900, 1100, 1400):
            self._radio(
                look, int(store["max_width"]) == n, f"最大宽度 {n}",
                lambda n=n: (store.__setitem__("max_width", n), store.save(), self.render()),
            )
        menu.add_cascade(label="外观", menu=look)
        menu.add_separator()

        stats = store["stats"]
        typed, errors = stats.get("typed", 0), stats.get("errors", 0)
        rate = 100.0 * (typed - errors) / typed if typed else 100.0
        menu.add_command(label=f"已练 {stats.get('words', 0)} 词 · 正确率 {rate:.1f}%", state="disabled")
        menu.add_command(label=f"{MARK_TICK if autostart_enabled() else '   '} 开机自启", command=self._toggle_autostart)
        menu.add_command(label=f"隐藏（{store['hotkey_toggle']} 唤回）", command=self.hide)
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit)

        x, y = self.root.winfo_pointerxy() if event is None else (event.x_root, event.y_root)
        menu.tk_popup(x, y)

    def _set_dock(self, mode: str) -> None:
        if mode == "free" and self.store["dock"] != "free":
            self.store["free_x"], self.store["free_y"] = self.root.winfo_x(), self.root.winfo_y()
        self.store["dock"] = mode
        self.store.save()
        self.reposition()

    def _set_theme(self, mode: str) -> None:
        self.store["theme"] = mode
        self.store.save()
        self.theme = palette(mode)
        self.root.configure(bg=self.theme["bg"])
        self.canvas.configure(bg=self.theme["bg"])
        self.render()

    def _set_font_size(self, n: int) -> None:
        self.store["font_size"] = n
        self.store.save()
        self.f_word.configure(size=n + 1)
        self.f_meta.configure(size=n - 2)
        self.f_text.configure(size=n - 1)
        self.f_icon.configure(size=n)
        self.height = self._bar_height()
        self.render()

    def _toggle_autostart(self) -> None:
        set_autostart(not autostart_enabled())

    # -------------------------------------------------------------- lifecycle

    def hide(self) -> None:
        self.hidden = True
        self.root.withdraw()

    def show(self) -> None:
        self.hidden = False
        self.root.deiconify()
        self._apply_window_styles()
        self.reposition()
        self._activate()

    def toggle(self) -> None:
        self.show() if self.hidden else self.hide()

    def _tick(self) -> None:
        if not self.hidden:
            try:
                winapi.assert_topmost(self._hwnd)
                if self.store["dock"] != "free":
                    self.reposition()
            except Exception:  # noqa: BLE001
                pass
        self.root.after(900, self._tick)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event == "toggle":
                    self.toggle()
                elif event == "boss":
                    self.hide()
                elif isinstance(event, tuple) and event[0] == "downloaded":
                    _, dict_id, ok, msg = event
                    if ok:
                        self.switch_dictionary(dict_id)
                    else:
                        self._flash(f"下载失败：{msg}", 2500)
        except queue.Empty:
            pass

        # A second launch drops this flag instead of starting a duplicate instance.
        if SHOW_FLAG.exists():
            try:
                SHOW_FLAG.unlink()
            except OSError:
                pass
            self.show()

        self.root.after(120, self._poll_events)

    def quit(self) -> None:
        self._persist()
        self.root.destroy()

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.mainloop()


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "QwertyBar"


def _launch_command() -> str:
    import sys

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve().parent.parent / "run.pyw"}"'


def autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(enable: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enable:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except OSError:
                pass
