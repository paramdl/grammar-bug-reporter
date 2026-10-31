"""
GrammarTool — System-wide AI grammar checker + Bug Report Generator
Hotkeys: Ctrl+Alt+G (grammar), Ctrl+Alt+B (bug reporter)
"""
import sys
import time
import queue
import threading
import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw, ImageFont

from config import load_config
from grammar_checker import get_selected_text, restore_and_paste
from live_checker import LiveChecker
from ui.overlay import GrammarOverlay
from ui.live_overlay import LiveSuggestion
from ui.bug_report import BugReportWindow
from ui.settings import SettingsWindow

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Modifier flags for Win32 RegisterHotKey
_HOTKEY_MODS = {
    "ctrl": 0x0002, "control": 0x0002, "alt": 0x0001,
    "shift": 0x0004, "win": 0x0008, "super": 0x0008,
}
_HOTKEY_SPECIAL = {f"f{i}": 0x70 + (i - 1) for i in range(1, 13)}  # F1..F12


def _parse_hotkey(combo: str):
    """Parse 'ctrl+alt+g' -> (modifier_flags, virtual_key_code)."""
    mods = 0
    vk = None
    for part in combo.lower().split("+"):
        part = part.strip()
        if not part:
            continue
        if part in _HOTKEY_MODS:
            mods |= _HOTKEY_MODS[part]
        elif part in _HOTKEY_SPECIAL:
            vk = _HOTKEY_SPECIAL[part]
        elif len(part) == 1:
            vk = ord(part.upper())
    return mods, vk


def _make_tray_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill="#7c3aed")
    # Draw a simple "G" shape
    d.rectangle([28, 28, 46, 34], fill="white")
    d.rectangle([40, 28, 46, 46], fill="white")
    d.arc([16, 16, 50, 50], start=30, end=330, fill="white", width=6)
    return img


class GrammarToolApp:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.title("Grammar Tool")

        self._overlay: GrammarOverlay | None = None
        self._bug_window: BugReportWindow | None = None
        self._settings_window: SettingsWindow | None = None
        self._live_bubble: LiveSuggestion | None = None

        # Thread-safe channel: the watcher thread posts UI events here, and the
        # main (GUI) thread drains them — never touch Tk from the worker thread.
        self._ui_queue: "queue.Queue" = queue.Queue()

        # Live desktop watcher (real-time, no hotkey)
        self._live = LiveChecker(
            on_suggestion=self._on_live_suggestion,
            on_context_lost=self._on_live_context_lost,
            on_rate_limited=self._on_live_rate_limited,
        )

        self._setup_tray()
        self._setup_hotkeys()
        self.root.after(100, self._pump_ui_events)

        # First-run: open settings if no API key; otherwise start live watching
        config = load_config()
        if not config.get("google_api_key"):
            self.root.after(600, self.show_settings)
        else:
            self._live.start()

    def _pump_ui_events(self):
        """Runs on the GUI thread; drains events posted by the watcher thread."""
        try:
            while True:
                evt = self._ui_queue.get_nowait()
                kind = evt[0]
                if kind == "suggest":
                    _, control, rect, original, corrected = evt
                    self._show_live_bubble(control, rect, original, corrected)
                elif kind == "dismiss":
                    self._close_live_bubble()
                elif kind == "rate":
                    secs = int(evt[1])
                    self._toast(
                        "Grammar Tool",
                        f"Gemini API limit/billing reached — live check paused "
                        f"~{secs}s. If it persists, check credits at ai.studio.",
                    )
        except queue.Empty:
            pass
        self.root.after(100, self._pump_ui_events)

    # ------------------------------------------------------------------ tray

    def _setup_tray(self):
        icon = pystray.Icon(
            "GrammarTool",
            _make_tray_icon(),
            "Grammar Tool",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Live Check (auto, as you type)",
                    self._toggle_live,
                    checked=lambda item: self._live.enabled,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Grammar Check  (Ctrl+Alt+G)",
                    lambda: self.root.after(0, self._trigger_grammar),
                ),
                pystray.MenuItem(
                    "Bug Reporter  (Ctrl+Alt+B)",
                    lambda: self.root.after(0, self.show_bug_reporter),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Settings",
                    lambda: self.root.after(0, self.show_settings),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._exit),
            ),
        )
        threading.Thread(target=icon.run, daemon=True).start()
        self._tray = icon

    # --------------------------------------------------------------- hotkeys

    def _setup_hotkeys(self):
        # Uses Win32 RegisterHotKey (event-based). Unlike a low-level keyboard
        # hook, this does NOT sit in the keystroke path, so it has zero effect
        # on normal typing.
        config = load_config()
        grammar_hk = config.get("grammar_hotkey", "ctrl+alt+g")
        bug_hk = config.get("bug_report_hotkey", "ctrl+alt+b")
        threading.Thread(
            target=self._hotkey_loop, args=(grammar_hk, bug_hk), daemon=True
        ).start()

    def _hotkey_loop(self, grammar_hk: str, bug_hk: str):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        WM_HOTKEY = 0x0312
        MOD_NOREPEAT = 0x4000

        registrations = {
            1: (grammar_hk, lambda: self.root.after(0, self._trigger_grammar)),
            2: (bug_hk, lambda: self.root.after(0, self.show_bug_reporter)),
        }
        actions = {}
        for hk_id, (combo, action) in registrations.items():
            mods, vk = _parse_hotkey(combo)
            if vk is None:
                continue
            if user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
                actions[hk_id] = action

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam in actions:
                actions[msg.wParam]()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _on_grammar_hotkey(self):
        # Runs in keyboard thread — capture text immediately while source app has focus
        time.sleep(0.15)
        text, hwnd = get_selected_text()
        self.root.after(0, lambda: self._trigger_grammar_with(text, hwnd))

    def _trigger_grammar(self):
        # Called from tray menu — need to re-capture from active window
        threading.Thread(target=self._on_grammar_hotkey, daemon=True).start()

    # --------------------------------------------------------- grammar check

    def _trigger_grammar_with(self, text: str, hwnd: int):
        if not text.strip():
            self._toast("No text selected", "Select some text first, then press Ctrl+Alt+G")
            return

        config = load_config()
        if not config.get("google_api_key"):
            self.show_settings()
            return

        if self._overlay and self._overlay.winfo_exists():
            self._overlay.destroy()

        self._overlay = GrammarOverlay(
            master=self.root,
            original_text=text,
            source_hwnd=hwnd,
            on_apply=self._apply_grammar,
        )
        self._overlay.start_analysis()

    def _apply_grammar(self, hwnd: int, improved_text: str):
        restore_and_paste(hwnd, improved_text)

    # ------------------------------------------------------------ live check

    def _toggle_live(self):
        enabled = self._live.toggle()
        # Starting fresh after first-run key entry
        if enabled and not self._live._thread.is_alive():
            self._live.start()
        title = "Grammar Tool"
        self._toast(title, "Live Check ON" if enabled else "Live Check OFF")

    def _on_live_suggestion(self, control, rect, original, corrected):
        # Called from the watcher thread — hand off via the thread-safe queue.
        self._ui_queue.put(("suggest", control, rect, original, corrected))

    def _on_live_context_lost(self):
        # Focus left the suggesting app — close the stale bubble.
        self._ui_queue.put(("dismiss",))

    def _on_live_rate_limited(self, seconds: float):
        self._ui_queue.put(("rate", seconds))

    def _close_live_bubble(self):
        if self._live_bubble and self._live_bubble.winfo_exists():
            self._live_bubble.destroy()
        self._live_bubble = None

    def _show_live_bubble(self, control, rect, original, corrected):
        self._close_live_bubble()

        def apply(fixed: str):
            self._live.request_apply(control, original, fixed)

        self._live_bubble = LiveSuggestion(
            master=self.root, rect=rect, original=original, corrected=corrected,
            on_apply=apply,
        )

    # ---------------------------------------------------------- bug reporter

    def show_bug_reporter(self):
        config = load_config()
        if not config.get("google_api_key"):
            self.show_settings()
            return

        if self._bug_window and self._bug_window.winfo_exists():
            self._bug_window.focus()
            return

        self._bug_window = BugReportWindow(master=self.root)

    # ---------------------------------------------------------------- settings

    def show_settings(self):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.focus()
            return
        self._settings_window = SettingsWindow(master=self.root)

    # ----------------------------------------------------------------- utils

    def _toast(self, title: str, message: str):
        popup = ctk.CTkToplevel(self.root)
        popup.title(title)
        popup.geometry("340x90")
        popup.attributes("-topmost", True)
        popup.configure(fg_color="#2a2a3e")
        popup.resizable(False, False)
        ctk.CTkLabel(
            popup, text=message, font=ctk.CTkFont(size=12),
            text_color="#e2e0f0", wraplength=300,
        ).pack(pady=24)
        popup.after(2500, popup.destroy)

    def _exit(self):
        self._tray.stop()
        self.root.quit()

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._exit()


if __name__ == "__main__":
    app = GrammarToolApp()
    app.run()
