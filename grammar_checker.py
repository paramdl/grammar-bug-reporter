import time
import pyperclip
import win32api
import win32con
import win32gui


def get_selected_text() -> tuple[str, int]:
    """
    Capture text selected in the currently focused app.
    Returns (selected_text, source_hwnd).
    Clears clipboard first so we can detect empty selection.
    """
    hwnd = win32gui.GetForegroundWindow()

    try:
        original = pyperclip.paste()
    except Exception:
        original = ""

    pyperclip.copy("\x00")  # sentinel so we detect nothing-was-selected
    time.sleep(0.05)

    # Simulate Ctrl+C via win32 to avoid conflicts with keyboard library hooks
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    time.sleep(0.04)
    win32api.keybd_event(ord("C"), 0, 0, 0)
    time.sleep(0.04)
    win32api.keybd_event(ord("C"), 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.04)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.25)

    try:
        text = pyperclip.paste()
    except Exception:
        text = ""

    if text == "\x00":
        text = ""

    # Restore original clipboard
    try:
        pyperclip.copy(original)
    except Exception:
        pass

    return text, hwnd


def restore_and_paste(hwnd: int, new_text: str):
    """
    Restore focus to source window and paste the replacement text.
    """
    pyperclip.copy(new_text)

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.15)

    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    time.sleep(0.04)
    win32api.keybd_event(ord("V"), 0, 0, 0)
    time.sleep(0.04)
    win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.04)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
