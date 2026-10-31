import threading
import webbrowser
import tkinter as tk
import customtkinter as ctk

from ai_client import generate_bug_report
import trello_client
from config import load_config

DARK_BG = "#1e1e2e"
CARD_BG = "#2a2a3e"
ACCENT = "#7c3aed"
SUCCESS_COLOR = "#4ade80"
ERROR_COLOR = "#f44336"
TEXT = "#e2e0f0"
MUTED = "#8888a8"
BORDER = "#3a3a5e"
SEVERITY_COLORS = {
    "Critical": "#ef4444",
    "High": "#f97316",
    "Medium": "#eab308",
    "Low": "#22c55e",
}


class BugReportWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)

        self.title("Bug Report Generator")
        self.geometry("700x780")
        self.minsize(600, 600)
        self.configure(fg_color=DARK_BG)
        self.attributes("-topmost", False)
        self.lift()
        self.focus()

        self._report: dict | None = None
        self._step_vars: list[ctk.StringVar] = []
        self._steps_frame = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build_ui(self):
        # Title bar
        header = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="  🐛  Bug Report Generator",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT,
        ).pack(side="left", padx=16, pady=14)

        # Prompt area
        prompt_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        prompt_frame.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            prompt_frame, text="Describe the bug:", font=ctk.CTkFont(size=12),
            text_color=MUTED, anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 4))

        self.prompt_input = ctk.CTkTextbox(
            prompt_frame, height=80, font=ctk.CTkFont(size=13),
            fg_color=DARK_BG, text_color=TEXT, border_color=BORDER, border_width=1,
            wrap="word",
        )
        self.prompt_input.pack(fill="x", padx=14, pady=(0, 4))
        self.prompt_input.insert(
            "1.0",
            "e.g. Login button doesn't respond when user has 2FA enabled on mobile Chrome",
        )
        self.prompt_input.bind("<FocusIn>", self._clear_placeholder)

        gen_row = ctk.CTkFrame(prompt_frame, fg_color="transparent")
        gen_row.pack(fill="x", padx=14, pady=(4, 12))

        self.gen_btn = ctk.CTkButton(
            gen_row, text="⚡  Generate Report", height=38,
            fg_color=ACCENT, hover_color="#6d28d9",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generate,
        )
        self.gen_btn.pack(side="right")

        self.status_label = ctk.CTkLabel(
            gen_row, text="", font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        self.status_label.pack(side="left")

        # Scrollable form
        self.form = ctk.CTkScrollableFrame(
            self, fg_color=DARK_BG, scrollbar_button_color=BORDER,
        )
        self.form.pack(fill="both", expand=True, padx=0, pady=0)

        # Title + Severity row
        row1 = ctk.CTkFrame(self.form, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(row1, text="Title", font=ctk.CTkFont(size=11), text_color=MUTED).pack(anchor="w")
        title_sev = ctk.CTkFrame(row1, fg_color="transparent")
        title_sev.pack(fill="x")
        self.title_var = ctk.StringVar()
        ctk.CTkEntry(
            title_sev, textvariable=self.title_var, height=36,
            font=ctk.CTkFont(size=13), fg_color=CARD_BG, text_color=TEXT,
            border_color=BORDER, border_width=1,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.severity_var = ctk.StringVar(value="Medium")
        sev_menu = ctk.CTkOptionMenu(
            title_sev, variable=self.severity_var,
            values=list(SEVERITY_COLORS.keys()),
            width=110, height=36,
            fg_color=CARD_BG, button_color=BORDER, button_hover_color=ACCENT,
            text_color=TEXT, font=ctk.CTkFont(size=12),
        )
        sev_menu.pack(side="right")

        # Description
        self._labeled_textbox("Description", "description_box", height=80)

        # Steps to reproduce
        steps_label_row = ctk.CTkFrame(self.form, fg_color="transparent")
        steps_label_row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(
            steps_label_row, text="Steps to Reproduce", font=ctk.CTkFont(size=11), text_color=MUTED,
        ).pack(side="left")
        ctk.CTkButton(
            steps_label_row, text="+ Add Step", width=80, height=24,
            fg_color="transparent", hover_color=BORDER, text_color=MUTED,
            border_width=1, border_color=BORDER, font=ctk.CTkFont(size=11),
            command=self._add_step,
        ).pack(side="right")

        self._steps_frame = ctk.CTkFrame(self.form, fg_color=CARD_BG, corner_radius=8)
        self._steps_frame.pack(fill="x", padx=16)

        # Actual / Expected
        self._labeled_textbox("Actual Result", "actual_box", height=60)
        self._labeled_textbox("Expected Result", "expected_box", height=60)

        # Environment
        env_row = ctk.CTkFrame(self.form, fg_color="transparent")
        env_row.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(env_row, text="Environment", font=ctk.CTkFont(size=11), text_color=MUTED).pack(anchor="w")
        self.env_var = ctk.StringVar()
        ctk.CTkEntry(
            env_row, textvariable=self.env_var, height=36,
            font=ctk.CTkFont(size=12), fg_color=CARD_BG, text_color=TEXT,
            border_color=BORDER, border_width=1, placeholder_text="OS, browser, app version…",
        ).pack(fill="x")

        # Labels
        lbl_row = ctk.CTkFrame(self.form, fg_color="transparent")
        lbl_row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(lbl_row, text="Labels", font=ctk.CTkFont(size=11), text_color=MUTED).pack(anchor="w")
        self.labels_var = ctk.StringVar()
        ctk.CTkEntry(
            lbl_row, textvariable=self.labels_var, height=34,
            font=ctk.CTkFont(size=12), fg_color=CARD_BG, text_color=TEXT,
            border_color=BORDER, border_width=1, placeholder_text="comma-separated labels",
        ).pack(fill="x")

        # Spacer
        ctk.CTkFrame(self.form, height=20, fg_color="transparent").pack()

        # Footer
        footer = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=64)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.trello_btn = ctk.CTkButton(
            footer, text="🎯  Create Trello Card", height=40, width=200,
            fg_color=ACCENT, hover_color="#6d28d9",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._create_trello,
        )
        self.trello_btn.pack(side="right", padx=(8, 16), pady=12)

        ctk.CTkButton(
            footer, text="📋  Copy", height=40, width=90,
            fg_color="transparent", hover_color=BORDER, text_color=MUTED,
            border_width=1, border_color=BORDER, font=ctk.CTkFont(size=12),
            command=self._copy_report,
        ).pack(side="right", padx=4, pady=12)

        self.footer_status = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        self.footer_status.pack(side="left", padx=16)

    def _labeled_textbox(self, label: str, attr: str, height: int):
        frame = ctk.CTkFrame(self.form, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11), text_color=MUTED).pack(anchor="w")
        box = ctk.CTkTextbox(
            frame, height=height, font=ctk.CTkFont(size=12), wrap="word",
            fg_color=CARD_BG, text_color=TEXT, border_color=BORDER, border_width=1,
        )
        box.pack(fill="x")
        setattr(self, attr, box)

    def _clear_placeholder(self, event):
        current = self.prompt_input.get("1.0", "end").strip()
        if current.startswith("e.g."):
            self.prompt_input.delete("1.0", "end")

    def _add_step(self, text: str = ""):
        idx = len(self._step_vars)
        var = ctk.StringVar(value=text)
        self._step_vars.append(var)

        row = ctk.CTkFrame(self._steps_frame, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(row, text=f"{idx + 1}.", width=24, font=ctk.CTkFont(size=12), text_color=MUTED).pack(
            side="left"
        )
        ctk.CTkEntry(
            row, textvariable=var, height=32,
            font=ctk.CTkFont(size=12), fg_color=DARK_BG, text_color=TEXT,
            border_color=BORDER, border_width=1,
        ).pack(side="left", fill="x", expand=True, padx=(4, 4))

        ctk.CTkButton(
            row, text="✕", width=26, height=26,
            fg_color="transparent", hover_color=BORDER, text_color=MUTED,
            command=lambda r=row, v=var: self._remove_step(r, v),
        ).pack(side="right")

    def _remove_step(self, row, var):
        if var in self._step_vars:
            self._step_vars.remove(var)
        row.destroy()

    def _generate(self):
        prompt = self.prompt_input.get("1.0", "end").strip()
        if not prompt or prompt.startswith("e.g."):
            self._set_status("Enter a bug description first.", error=True)
            return

        self.gen_btn.configure(state="disabled", text="Generating…")
        self._set_status("Contacting Claude API…")
        threading.Thread(target=self._do_generate, args=(prompt,), daemon=True).start()

    def _do_generate(self, prompt: str):
        try:
            report = generate_bug_report(prompt)
            self.after(0, lambda: self._populate_form(report))
        except Exception as e:
            self.after(0, lambda: self._set_status(f"Error: {e}", error=True))
            self.after(0, lambda: self.gen_btn.configure(state="normal", text="⚡  Generate Report"))

    def _populate_form(self, report: dict):
        self._report = report

        self.title_var.set(report.get("title", ""))
        self.severity_var.set(report.get("severity", "Medium"))

        for box, key in [
            (self.description_box, "description"),
            (self.actual_box, "actual_result"),
            (self.expected_box, "expected_result"),
        ]:
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", report.get(key, ""))

        # Rebuild steps
        for w in self._steps_frame.winfo_children():
            w.destroy()
        self._step_vars.clear()
        for step in report.get("steps_to_reproduce", []):
            self._add_step(step)

        self.env_var.set(report.get("environment", ""))
        self.labels_var.set(", ".join(report.get("labels", [])))

        self.gen_btn.configure(state="normal", text="⚡  Regenerate")
        self._set_status("Report generated — review and edit fields below.", error=False)

    def _build_report_dict(self) -> dict:
        return {
            "title": self.title_var.get().strip(),
            "severity": self.severity_var.get(),
            "description": self.description_box.get("1.0", "end").strip(),
            "steps_to_reproduce": [v.get().strip() for v in self._step_vars if v.get().strip()],
            "actual_result": self.actual_box.get("1.0", "end").strip(),
            "expected_result": self.expected_box.get("1.0", "end").strip(),
            "environment": self.env_var.get().strip(),
            "labels": [l.strip() for l in self.labels_var.get().split(",") if l.strip()],
        }

    def _create_trello(self):
        report = self._build_report_dict()
        if not report["title"]:
            self._set_footer("Generate or fill in a report first.", error=True)
            return

        config = load_config()
        if not config.get("trello_list_id"):
            self._set_footer("Trello not configured. Open Settings.", error=True)
            return

        self.trello_btn.configure(state="disabled", text="Creating…")
        threading.Thread(target=self._do_create_trello, args=(report,), daemon=True).start()

    def _do_create_trello(self, report: dict):
        try:
            card = trello_client.create_bug_card(report)
            self.after(0, lambda: self._show_trello_success(card))
        except Exception as e:
            self.after(0, lambda: self._set_footer(f"Trello error: {e}", error=True))
            self.after(0, lambda: self.trello_btn.configure(state="normal", text="🎯  Create Trello Card"))

    def _show_trello_success(self, card: dict):
        self.trello_btn.configure(state="normal", text="🎯  Create Trello Card")
        url = card.get("url", "")

        # Replace footer status with a link button
        self.footer_status.configure(
            text=f"✓ Card created!  {url}",
            text_color=SUCCESS_COLOR, cursor="hand2",
        )
        self.footer_status.bind("<Button-1>", lambda e: webbrowser.open(url))

    def _copy_report(self):
        import pyperclip
        report = self._build_report_dict()
        steps = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(report["steps_to_reproduce"]))
        text = (
            f"Title: {report['title']}\n"
            f"Severity: {report['severity']}\n\n"
            f"Description:\n{report['description']}\n\n"
            f"Steps to Reproduce:\n{steps}\n\n"
            f"Actual Result:\n{report['actual_result']}\n\n"
            f"Expected Result:\n{report['expected_result']}\n\n"
            f"Environment: {report['environment']}\n"
            f"Labels: {', '.join(report['labels'])}"
        )
        pyperclip.copy(text)
        self._set_footer("Copied to clipboard!")

    def _set_status(self, msg: str, error: bool = False):
        self.status_label.configure(
            text=msg,
            text_color=ERROR_COLOR if error else MUTED,
        )

    def _set_footer(self, msg: str, error: bool = False):
        self.footer_status.configure(
            text=msg,
            text_color=ERROR_COLOR if error else SUCCESS_COLOR,
        )
        self.footer_status.unbind("<Button-1>")
