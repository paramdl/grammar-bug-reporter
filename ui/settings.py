import threading
import customtkinter as ctk

from config import load_config, save_config
import trello_client

DARK_BG = "#1e1e2e"
CARD_BG = "#2a2a3e"
ACCENT = "#7c3aed"
TEXT = "#e2e0f0"
MUTED = "#8888a8"
BORDER = "#3a3a5e"
SUCCESS_COLOR = "#4ade80"
ERROR_COLOR = "#f44336"


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Settings")
        self.geometry("540x640")
        self.resizable(False, False)
        self.configure(fg_color=DARK_BG)
        self.lift()
        self.focus()

        self._boards: list[dict] = []
        self._lists: list[dict] = []
        self._config = load_config()

        self._build_ui()
        self._load_values()

    def _section(self, title: str):
        ctk.CTkLabel(
            self.form, text=title,
            font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED,
        ).pack(fill="x", padx=16, pady=(20, 6))
        ctk.CTkFrame(self.form, height=1, fg_color=BORDER).pack(fill="x", padx=16, pady=(0, 8))

    def _field(self, label: str, show: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(
            self.form, text=label, font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w",
        ).pack(fill="x", padx=16, pady=(4, 2))
        entry = ctk.CTkEntry(
            self.form, height=36, font=ctk.CTkFont(size=12),
            fg_color=CARD_BG, text_color=TEXT, border_color=BORDER, border_width=1,
            show=show,
        )
        entry.pack(fill="x", padx=16)
        return entry

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="  ⚙  Settings",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT,
        ).pack(side="left", padx=16, pady=14)

        self.form = ctk.CTkScrollableFrame(self, fg_color=DARK_BG, scrollbar_button_color=BORDER)
        self.form.pack(fill="both", expand=True)

        # Google AI Studio
        self._section("Google AI Studio API")
        self.google_entry = self._field("API Key (AIza…)", show="•")
        ctk.CTkLabel(
            self.form,
            text="Get your key at aistudio.google.com/apikey",
            font=ctk.CTkFont(size=10), text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(2, 0))

        # Trello
        self._section("Trello Integration")
        self.trello_key_entry = self._field("API Key")
        self.trello_token_entry = self._field("Token", show="•")
        ctk.CTkLabel(
            self.form,
            text="Get key+token at trello.com/app-key",
            font=ctk.CTkFont(size=10), text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(2, 8))

        self.connect_btn = ctk.CTkButton(
            self.form, text="Connect & Load Boards", height=34, width=200,
            fg_color=ACCENT, hover_color="#6d28d9", font=ctk.CTkFont(size=12),
            command=self._connect_trello,
        )
        self.connect_btn.pack(anchor="w", padx=16)

        self.trello_status = ctk.CTkLabel(
            self.form, text="", font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        self.trello_status.pack(anchor="w", padx=16, pady=(4, 0))

        ctk.CTkLabel(
            self.form, text="Board", font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 2))
        self.board_var = ctk.StringVar(value="— connect first —")
        self.board_menu = ctk.CTkOptionMenu(
            self.form, variable=self.board_var, values=["— connect first —"],
            height=36, fg_color=CARD_BG, button_color=BORDER, button_hover_color=ACCENT,
            text_color=TEXT, font=ctk.CTkFont(size=12),
            command=self._on_board_select,
        )
        self.board_menu.pack(fill="x", padx=16)

        ctk.CTkLabel(
            self.form, text="List (where cards are created)", font=ctk.CTkFont(size=11),
            text_color=MUTED, anchor="w",
        ).pack(fill="x", padx=16, pady=(10, 2))
        self.list_var = ctk.StringVar(value="— select board first —")
        self.list_menu = ctk.CTkOptionMenu(
            self.form, variable=self.list_var, values=["— select board first —"],
            height=36, fg_color=CARD_BG, button_color=BORDER, button_hover_color=ACCENT,
            text_color=TEXT, font=ctk.CTkFont(size=12),
        )
        self.list_menu.pack(fill="x", padx=16)

        # Live Check
        self._section("Live Check (auto, as you type)")
        self.live_enabled_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self.form, text="Enable live checking", variable=self.live_enabled_var,
            font=ctk.CTkFont(size=12), text_color=TEXT,
            fg_color=ACCENT, hover_color="#6d28d9",
        ).pack(anchor="w", padx=16, pady=(4, 8))
        self.live_apps_entry = self._field("Run ONLY in these apps (comma-separated .exe)")
        ctk.CTkLabel(
            self.form,
            text="Leave blank to run everywhere. Keeps it out of Claude, terminals, editors.",
            font=ctk.CTkFont(size=10), text_color=MUTED, wraplength=480, justify="left",
        ).pack(anchor="w", padx=16, pady=(2, 0))

        # Hotkeys
        self._section("Hotkeys")
        self.grammar_hotkey_entry = self._field("Grammar Check Hotkey")
        self.bug_hotkey_entry = self._field("Bug Reporter Hotkey")

        ctk.CTkFrame(self.form, height=20, fg_color="transparent").pack()

        # Footer
        footer = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=60)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer, text="Save Settings", height=40, width=140,
            fg_color=ACCENT, hover_color="#6d28d9",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save,
        ).pack(side="right", padx=(8, 16), pady=10)

        self.save_status = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        self.save_status.pack(side="left", padx=16)

    def _load_values(self):
        c = self._config
        self.google_entry.insert(0, c.get("google_api_key", ""))
        self.trello_key_entry.insert(0, c.get("trello_api_key", ""))
        self.trello_token_entry.insert(0, c.get("trello_token", ""))
        self.grammar_hotkey_entry.insert(0, c.get("grammar_hotkey", "ctrl+alt+g"))
        self.bug_hotkey_entry.insert(0, c.get("bug_report_hotkey", "ctrl+alt+b"))
        self.live_enabled_var.set(bool(c.get("live_enabled", True)))
        self.live_apps_entry.insert(0, ", ".join(c.get("live_apps", [])))

        if c.get("trello_board_name"):
            self.board_var.set(c["trello_board_name"])
        if c.get("trello_list_name"):
            self.list_var.set(c["trello_list_name"])

    def _connect_trello(self):
        key = self.trello_key_entry.get().strip()
        token = self.trello_token_entry.get().strip()
        if not key or not token:
            self.trello_status.configure(text="Enter API key and token first.", text_color=ERROR_COLOR)
            return

        # Temporarily save so trello_client picks them up
        c = load_config()
        c["trello_api_key"] = key
        c["trello_token"] = token
        save_config(c)

        self.connect_btn.configure(state="disabled", text="Loading…")
        self.trello_status.configure(text="Fetching boards…", text_color=MUTED)
        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        try:
            boards = trello_client.get_boards()
            self.after(0, lambda: self._populate_boards(boards))
        except Exception as e:
            self.after(0, lambda: self.trello_status.configure(
                text=f"Error: {e}", text_color=ERROR_COLOR
            ))
            self.after(0, lambda: self.connect_btn.configure(state="normal", text="Connect & Load Boards"))

    def _populate_boards(self, boards: list[dict]):
        self._boards = boards
        names = [b["name"] for b in boards]
        self.board_menu.configure(values=names)
        if names:
            self.board_var.set(names[0])
            self._on_board_select(names[0])
        self.trello_status.configure(
            text=f"✓ Connected — {len(boards)} board(s) found", text_color=SUCCESS_COLOR
        )
        self.connect_btn.configure(state="normal", text="Refresh Boards")

    def _on_board_select(self, name: str):
        board = next((b for b in self._boards if b["name"] == name), None)
        if not board:
            return
        self._selected_board = board
        self.list_var.set("Loading lists…")
        threading.Thread(target=self._do_load_lists, args=(board["id"],), daemon=True).start()

    def _do_load_lists(self, board_id: str):
        try:
            lists = trello_client.get_lists(board_id)
            self.after(0, lambda: self._populate_lists(lists))
        except Exception as e:
            self.after(0, lambda: self.list_var.set(f"Error: {e}"))

    def _populate_lists(self, lists: list[dict]):
        self._lists = lists
        names = [l["name"] for l in lists]
        self.list_menu.configure(values=names)
        if names:
            self.list_var.set(names[0])

    def _save(self):
        c = load_config()
        c["google_api_key"] = self.google_entry.get().strip()
        c["trello_api_key"] = self.trello_key_entry.get().strip()
        c["trello_token"] = self.trello_token_entry.get().strip()
        c["grammar_hotkey"] = self.grammar_hotkey_entry.get().strip() or "ctrl+alt+g"
        c["bug_report_hotkey"] = self.bug_hotkey_entry.get().strip() or "ctrl+alt+b"
        c["live_enabled"] = bool(self.live_enabled_var.get())
        c["live_apps"] = [
            a.strip().lower()
            for a in self.live_apps_entry.get().split(",")
            if a.strip()
        ]

        board_name = self.board_var.get()
        board = next((b for b in self._boards if b["name"] == board_name), None)
        if board:
            c["trello_board_id"] = board["id"]
            c["trello_board_name"] = board["name"]

        list_name = self.list_var.get()
        lst = next((l for l in self._lists if l["name"] == list_name), None)
        if lst:
            c["trello_list_id"] = lst["id"]
            c["trello_list_name"] = lst["name"]

        save_config(c)
        self.save_status.configure(text="✓ Saved! Restart to apply hotkey changes.", text_color=SUCCESS_COLOR)
