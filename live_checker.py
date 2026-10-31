"""
Live desktop grammar watcher.

Runs in a background thread. Uses Windows UI Automation to read whatever
editable text field currently has focus (works across most desktop apps and
browsers, not just one). When you pause typing, it checks the text with Gemini
and — if there are mistakes — asks the app to show a floating suggestion bubble.
No hotkey required.

Hard limits (true for any program, Grammarly included):
  * Cannot draw underlines inside another app's text box — we float a bubble.
  * Cannot read apps that don't expose their text to UI Automation
    (some games / custom-drawn editors). Those are skipped silently.
"""
import os
import time
import queue
import ctypes
import threading
from ctypes import wintypes

import pyperclip
import win32api
import win32con
import win32gui
import win32process
import uiautomation as auto

from ai_client import live_check, QuotaExceeded
from config import load_config

POLL_INTERVAL = 0.35      # seconds between focus polls
STABLE_DELAY = 1.1        # text must be unchanged this long before we check
MIN_LENGTH = 15           # don't check very short fragments
MIN_API_INTERVAL = 1.5    # min seconds between Gemini calls (Tier 1 = 1000/min,
                          # so this is for sanity, not to dodge the free limit)
CONFIG_RELOAD = 3.0       # re-read config (app list) this often

# Control types we treat as editable text surfaces.
EDITABLE_TYPES = {"EditControl", "DocumentControl", "ComboBoxControl"}


def process_name(pid: int) -> str:
    """Return the lowercase executable name for a PID, e.g. 'ms-teams.exe'."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(4096)
        size = wintypes.DWORD(4096)
        ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
            h, 0, buf, ctypes.byref(size)
        )
        if ok:
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


class LiveChecker:
    def __init__(self, on_suggestion, on_context_lost=None,
                 on_rate_limited=None, debug=False):
        """on_suggestion(control, rect, original, corrected) is invoked from the
        watcher thread when a fix is found. on_context_lost() is invoked when
        focus leaves the app a suggestion was made for (so the bubble can close).
        on_rate_limited(seconds) fires when the API quota is hit. All are called
        from the watcher thread — the callback marshals to the GUI thread."""
        self.on_suggestion = on_suggestion
        self.on_context_lost = on_context_lost
        self.on_rate_limited = on_rate_limited
        self.debug = debug
        self.enabled = True

        self._cooldown_until = 0.0    # pause API calls until this time (429)

        self._own_pid = os.getpid()
        self._apply_q: "queue.Queue" = queue.Queue()
        self._last_checked = ""       # last text we sent to the API
        self._last_api_time = 0.0

        # App allowlist (reloaded from config periodically)
        self._allowed_apps: set[str] = set()
        self._config_enabled = True
        self._last_config_load = 0.0
        self._reload_config()

        # Track the app a live suggestion is currently shown for.
        self._suggest_pid: int | None = None
        self._focused_app_pid: int | None = None

        self._thread = threading.Thread(target=self._run, daemon=True)

    def _log(self, *a):
        if self.debug:
            print("[live]", *a, flush=True)

    def _reload_config(self):
        try:
            cfg = load_config()
            self._allowed_apps = {
                a.strip().lower() for a in cfg.get("live_apps", []) if a.strip()
            }
            self._config_enabled = bool(cfg.get("live_enabled", True))
        except Exception:
            pass
        self._last_config_load = time.time()

    # ------------------------------------------------------------------ public

    def start(self):
        self._thread.start()

    def set_enabled(self, value: bool):
        self.enabled = value
        if not value:
            self._last_checked = ""

    def toggle(self) -> bool:
        self.set_enabled(not self.enabled)
        return self.enabled

    def request_apply(self, control, original: str, corrected: str):
        """Called from the GUI thread when the user clicks Apply. The actual
        UIA write happens on the watcher thread (COM objects are thread-bound)."""
        self._apply_q.put((control, original, corrected))

    def note_applied(self, corrected: str):
        # Prevent the just-applied text from being re-flagged immediately.
        self._last_checked = corrected

    # ------------------------------------------------------------------ worker

    def _run(self):
        auto.SetGlobalSearchTimeout(0.4)
        prev_text = None
        stable_since = 0.0

        while True:
            self._drain_apply_queue()

            if time.time() - self._last_config_load > CONFIG_RELOAD:
                self._reload_config()

            if not self.enabled or not self._config_enabled:
                time.sleep(0.3)
                continue

            ctrl = self._focused_editable()
            if ctrl is None:
                prev_text = None
                time.sleep(POLL_INTERVAL)
                continue

            text = self._read_value(ctrl)
            if text is None:
                self._log("focused editable but value unreadable")
                prev_text = None
                time.sleep(POLL_INTERVAL)
                continue

            now = time.time()
            if text != prev_text:
                prev_text = text
                stable_since = now
                time.sleep(POLL_INTERVAL)
                continue

            # Text has been stable — decide whether to check it.
            if (
                now >= self._cooldown_until
                and len(text.strip()) >= MIN_LENGTH
                and text != self._last_checked
                and now - stable_since >= STABLE_DELAY
                and now - self._last_api_time >= MIN_API_INTERVAL
            ):
                self._last_api_time = now
                self._log(f"checking ({len(text)} chars): {text[:50]!r}")
                ok = self._check_and_notify(ctrl, text)
                # Only remember this text as "checked" if the API actually
                # answered. On a transient error (503) we leave it unmarked so
                # the next stable cycle retries — instead of skipping forever.
                if ok:
                    self._last_checked = text

            time.sleep(POLL_INTERVAL)

    # --------------------------------------------------------------- internals

    def _current_app(self):
        """Return (exe_name, pid) of the FOREGROUND window's process — i.e. the
        real app the user is in. We use this, not the focused control's process,
        because modern apps host their text box in a child process (Teams uses
        msedgewebview2.exe, Electron apps use renderer children). The foreground
        window always belongs to the main app (ms-teams.exe, chrome.exe, ...)."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return process_name(pid), pid
        except Exception:
            return "", None

    def _focused_editable(self):
        app_exe, app_pid = self._current_app()
        self._focused_app_pid = app_pid

        if app_pid == self._own_pid:
            return None  # our own window (e.g. the bubble) is focused

        # If a suggestion is showing and focus moved to a different app,
        # ask the app to close the stale bubble.
        if self._suggest_pid is not None and app_pid != self._suggest_pid:
            self._suggest_pid = None
            if self.on_context_lost:
                self.on_context_lost()

        # App allowlist — only run in the apps the user chose.
        if self._allowed_apps and app_exe and app_exe not in self._allowed_apps:
            return None

        try:
            ctrl = auto.GetFocusedControl()
        except Exception:
            return None
        if ctrl is None:
            return None
        try:
            if ctrl.ProcessId == self._own_pid:
                return None
        except Exception:
            pass

        try:
            ctype = ctrl.ControlTypeName
        except Exception:
            return None
        if ctype not in EDITABLE_TYPES:
            self._log(f"focused control not editable: {ctype}")
            return None
        return ctrl

    def _read_value(self, ctrl):
        """Return the field's current text, or None if it can't/shouldn't be read."""
        try:
            vp = ctrl.GetValuePattern()
        except Exception:
            return None
        if vp is None:
            return None
        try:
            if getattr(vp, "IsReadOnly", False):
                return None
        except Exception:
            pass
        try:
            value = vp.Value
        except Exception:
            return None
        return value or ""

    def _check_and_notify(self, ctrl, text) -> bool:
        """Returns True if the API answered (whether or not errors were found),
        False on a transient API error so the caller can retry."""
        try:
            result = live_check(text)
        except QuotaExceeded as e:
            # Free-tier rate limit hit — stop calling for a while.
            self._cooldown_until = time.time() + e.retry_after
            self._log(f"RATE LIMITED — cooling down {e.retry_after:.0f}s")
            if self.on_rate_limited:
                self.on_rate_limited(e.retry_after)
            return False
        except Exception as e:
            self._log(f"live_check API error: {type(e).__name__}: {e}")
            return False
        if not result or not result.get("has_errors"):
            self._log("no errors found")
            return True
        corrected = (result.get("corrected") or "").strip()
        if not corrected or corrected == text.strip():
            self._log("corrected == original, skipping")
            return True
        self._log(f"SUGGESTING: {corrected[:60]!r}")
        try:
            rect = ctrl.BoundingRectangle
            rect = (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            rect = None
        self._suggest_pid = self._focused_app_pid
        self.on_suggestion(ctrl, rect, text, corrected)
        return True

    def _drain_apply_queue(self):
        while True:
            try:
                ctrl, original, corrected = self._apply_q.get_nowait()
            except queue.Empty:
                return
            self._apply_text(ctrl, original, corrected)
            self._suggest_pid = None

    def _apply_text(self, ctrl, original, corrected):
        """Replace the field's text. Tries UIA SetValue (clean, for classic
        Win32 edits); if that doesn't take — the case for Chromium / Electron
        contenteditable boxes like Teams, Slack, Discord, and most web chats —
        falls back to the universal clipboard method (focus, select-all, paste).

        Guarded: it only writes if the target field STILL holds the exact text
        we suggested a fix for. If focus moved elsewhere or you kept typing, it
        aborts rather than clobbering the wrong content (e.g. a reply thread)."""
        # Fast path: UIA SetValue, guarded + verified.
        try:
            vp = ctrl.GetValuePattern()
            cur = vp.Value or ""
            if cur.strip() and original.strip() and cur.strip() != original.strip():
                self._log("field changed since suggestion — aborting apply")
                self._last_checked = ""
                return
            vp.SetValue(corrected)
            time.sleep(0.05)
            if (vp.Value or "").strip() == corrected.strip():
                self._log("applied via SetValue")
                self._last_checked = corrected
                return
        except Exception:
            pass

        # Universal path: focus the field, verify it's the right one, paste.
        self._log("SetValue didn't take — applying via clipboard/keystrokes")
        try:
            ctrl.SetFocus()
        except Exception:
            pass
        time.sleep(0.12)

        # SAFETY GUARD: confirm the currently-focused field still holds the
        # original text before we select-all + paste. This is what stops Apply
        # from overwriting the wrong box (reply thread, another message, etc.).
        try:
            foc = auto.GetFocusedControl()
            fv = foc.GetValuePattern().Value or ""
            if fv.strip() and original.strip() and fv.strip() != original.strip():
                self._log("focused field mismatch — aborting to avoid clobber")
                self._last_checked = ""
                return
        except Exception:
            pass  # can't verify (rare) — proceed best-effort

        try:
            saved_clip = pyperclip.paste()
        except Exception:
            saved_clip = None
        try:
            pyperclip.copy(corrected)
        except Exception:
            self._log("clipboard copy failed")
            return
        time.sleep(0.06)
        _send_ctrl_key(0x41)   # Ctrl+A  (select all in the field)
        time.sleep(0.05)
        _send_ctrl_key(0x56)   # Ctrl+V  (paste)
        time.sleep(0.18)
        self._last_checked = corrected
        if saved_clip is not None:
            try:
                pyperclip.copy(saved_clip)
            except Exception:
                pass


def _send_ctrl_key(vk_code: int):
    """Send Ctrl + <key> via low-level key events (works in any app)."""
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
