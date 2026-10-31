import threading
import tkinter as tk
import customtkinter as ctk
import win32api

from ai_client import improve_grammar

TONES = ["professional", "casual", "polite", "concise"]
SEVERITY_COLOR = {"✓": "#4caf50", "!": "#ff9800", "✗": "#f44336"}

DARK_BG = "#1e1e2e"
CARD_BG = "#2a2a3e"
ACCENT = "#7c3aed"
TEXT = "#e2e0f0"
MUTED = "#8888a8"
SUCCESS = "#4ade80"
BORDER = "#3a3a5e"


class GrammarOverlay(ctk.CTkToplevel):
    def __init__(self, master, original_text: str, source_hwnd: int, on_apply):
        super().__init__(master)

        self.original_text = original_text
        self.source_hwnd = source_hwnd
        self.on_apply = on_apply
        self.result: dict | None = None
        self.selected_tone = ctk.StringVar(value="professional")

        self.title("Grammar Suggestion")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color=DARK_BG)
        self._position_near_cursor()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.dismiss)

    def _position_near_cursor(self):
        self.update_idletasks()
        x, y = win32api.GetCursorPos()
        w, h = 520, 400
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = min(x + 16, sw - w - 10)
        y = min(y + 16, sh - h - 48)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        pad = {"padx": 16, "pady": 8}

        # Header
        header = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="  Grammar Suggestion", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT, anchor="w",
        ).pack(side="left", padx=12, pady=10)
        ctk.CTkButton(
            header, text="✕", width=28, height=28, fg_color="transparent",
            hover_color="#3a3a5e", text_color=MUTED, command=self.dismiss,
        ).pack(side="right", padx=6, pady=6)

        body = ctk.CTkScrollableFrame(self, fg_color=DARK_BG, scrollbar_button_color=BORDER)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # Original text
        ctk.CTkLabel(body, text="Original:", font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w").pack(
            fill="x", padx=16, pady=(12, 2)
        )
        orig_preview = self.original_text[:200] + ("…" if len(self.original_text) > 200 else "")
        ctk.CTkLabel(
            body, text=orig_preview, wraplength=460, justify="left",
            font=ctk.CTkFont(size=12), text_color="#aaaacc", anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 8))

        # Tone selector
        tone_row = ctk.CTkFrame(body, fg_color="transparent")
        tone_row.pack(fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(tone_row, text="Tone:", font=ctk.CTkFont(size=11), text_color=MUTED).pack(side="left")
        for t in TONES:
            ctk.CTkRadioButton(
                tone_row, text=t.capitalize(), variable=self.selected_tone, value=t,
                font=ctk.CTkFont(size=11), text_color=TEXT,
                fg_color=ACCENT, hover_color="#6d28d9",
                command=self._on_tone_change,
            ).pack(side="left", padx=(10, 0))

        # Divider
        ctk.CTkFrame(body, height=1, fg_color=BORDER).pack(fill="x", padx=16, pady=4)

        # Suggestion area
        ctk.CTkLabel(
            body, text="Improved:", font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w"
        ).pack(fill="x", padx=16, pady=(8, 2))

        self.suggestion_box = ctk.CTkTextbox(
            body, height=110, font=ctk.CTkFont(size=13), wrap="word",
            fg_color=CARD_BG, text_color=TEXT, border_color=BORDER, border_width=1,
        )
        self.suggestion_box.pack(fill="x", padx=16, pady=(0, 8))
        self.suggestion_box.insert("1.0", "Analyzing…")
        self.suggestion_box.configure(state="disabled")

        # Changes list
        self.changes_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.changes_frame.pack(fill="x", padx=16, pady=(0, 12))

        # Footer buttons
        footer = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0)
        footer.pack(fill="x", side="bottom")

        self.apply_btn = ctk.CTkButton(
            footer, text="✓  Apply", width=120, height=36,
            fg_color=ACCENT, hover_color="#6d28d9", text_color="white",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.apply, state="disabled",
        )
        self.apply_btn.pack(side="right", padx=(8, 16), pady=10)

        ctk.CTkButton(
            footer, text="Dismiss", width=90, height=36,
            fg_color="transparent", hover_color=BORDER, text_color=MUTED,
            border_width=1, border_color=BORDER,
            command=self.dismiss,
        ).pack(side="right", padx=4, pady=10)

        self.status_label = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=11), text_color=MUTED
        )
        self.status_label.pack(side="left", padx=16)

    def start_analysis(self):
        tone = self.selected_tone.get()
        threading.Thread(target=self._run_analysis, args=(tone,), daemon=True).start()

    def _run_analysis(self, tone: str):
        try:
            result = improve_grammar(self.original_text, tone)
            self.after(0, lambda: self._show_result(result))
        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _show_result(self, result: dict):
        self.result = result

        self.suggestion_box.configure(state="normal")
        self.suggestion_box.delete("1.0", "end")
        self.suggestion_box.insert("1.0", result.get("improved", ""))
        self.suggestion_box.configure(state="normal")  # keep editable

        # Clear and rebuild changes
        for w in self.changes_frame.winfo_children():
            w.destroy()

        changes = result.get("changes", [])
        if changes:
            for change in changes[:4]:
                ctk.CTkLabel(
                    self.changes_frame, text=f"  • {change}",
                    font=ctk.CTkFont(size=11), text_color=MUTED,
                    anchor="w",
                ).pack(fill="x")

        score = result.get("tone_score", 0)
        has_errors = result.get("has_errors", False)
        status = f"Tone score: {score}/10"
        if has_errors:
            status += "  •  Errors fixed"
        self.status_label.configure(text=status)
        self.apply_btn.configure(state="normal")

    def _show_error(self, msg: str):
        self.suggestion_box.configure(state="normal")
        self.suggestion_box.delete("1.0", "end")
        self.suggestion_box.insert("1.0", f"Error: {msg}")
        self.suggestion_box.configure(state="disabled")
        self.status_label.configure(text="Failed", text_color="#f44336")

    def _on_tone_change(self):
        if not self.winfo_exists():
            return
        self.result = None
        self.apply_btn.configure(state="disabled")
        self.suggestion_box.configure(state="normal")
        self.suggestion_box.delete("1.0", "end")
        self.suggestion_box.insert("1.0", "Analyzing…")
        self.suggestion_box.configure(state="disabled")
        self.status_label.configure(text="")
        self.start_analysis()

    def apply(self):
        if not self.result:
            return
        # Get current text from box (user may have edited it)
        improved = self.suggestion_box.get("1.0", "end").strip()
        self.withdraw()
        self.after(100, lambda: self._do_apply(improved))

    def _do_apply(self, text: str):
        self.on_apply(self.source_hwnd, text)
        self.destroy()

    def dismiss(self):
        self.destroy()
