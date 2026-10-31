"""Floating, non-intrusive suggestion bubble shown near the text field.

Appears when the live checker finds mistakes. Shows the corrected text with
Apply / Ignore. Auto-dismisses after a timeout so it never lingers.
"""
import customtkinter as ctk

DARK_BG = "#1e1e2e"
CARD_BG = "#2a2a3e"
ACCENT = "#7c3aed"
TEXT = "#e2e0f0"
MUTED = "#8888a8"
SUCCESS = "#4ade80"
BORDER = "#3a3a5e"

AUTO_DISMISS_MS = 12000
WIDTH = 380


class LiveSuggestion(ctk.CTkToplevel):
    def __init__(self, master, rect, original, corrected, on_apply, on_dismiss=None):
        super().__init__(master)
        self._on_apply = on_apply
        self._on_dismiss = on_dismiss
        self._corrected = corrected

        self.overrideredirect(True)          # borderless bubble
        self.attributes("-topmost", True)
        self.configure(fg_color=BORDER)      # acts as 1px border
        self._build(corrected)
        self._place(rect)

        self._timer = self.after(AUTO_DISMISS_MS, self._dismiss)

    def _build(self, corrected):
        inner = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=8)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            header, text="✓  Suggestion", text_color=SUCCESS,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header, text="✕", width=22, height=22, fg_color="transparent",
            hover_color=BORDER, text_color=MUTED, font=ctk.CTkFont(size=12),
            command=self._dismiss,
        ).pack(side="right")

        box = ctk.CTkTextbox(
            inner, height=88, width=WIDTH - 24, wrap="word",
            fg_color=DARK_BG, text_color=TEXT, border_width=0,
            font=ctk.CTkFont(size=12),
        )
        box.insert("1.0", corrected)
        box.configure(state="disabled")
        box.pack(fill="x", padx=12, pady=(0, 8))

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(
            btns, text="Ignore", width=80, height=30, fg_color="transparent",
            border_width=1, border_color=BORDER, text_color=MUTED,
            hover_color=BORDER, font=ctk.CTkFont(size=12),
            command=self._dismiss,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            btns, text="Apply fix", width=100, height=30, fg_color=ACCENT,
            hover_color="#6d28d9", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._apply,
        ).pack(side="right")

    def _place(self, rect):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        if rect:
            left, top, right, bottom = rect
            x, y = left, bottom + 6           # just below the field
            if y + h > sh:                    # not enough room below → above
                y = max(0, top - h - 6)
            x = max(0, min(x, sw - w))
        else:
            x, y = sw - w - 40, sh - h - 80    # fallback: bottom-right

        self.geometry(f"+{int(x)}+{int(y)}")

    def _apply(self):
        try:
            self._on_apply(self._corrected)
        finally:
            self._close()

    def _dismiss(self):
        if self._on_dismiss:
            self._on_dismiss()
        self._close()

    def _close(self):
        try:
            self.after_cancel(self._timer)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
