import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".grammar_tool"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "google_api_key": os.environ.get("GOOGLE_API_KEY", ""),
    "trello_api_key": os.environ.get("TRELLO_API_KEY", ""),
    "trello_token": os.environ.get("TRELLO_TOKEN", ""),
    "trello_board_id": os.environ.get("TRELLO_BOARD_ID", ""),
    "trello_list_id": "",
    "trello_board_name": "",
    "trello_list_name": "",
    "grammar_hotkey": "ctrl+alt+g",
    "bug_report_hotkey": "ctrl+alt+b",
    "default_tone": "professional",
    # Live Check runs ONLY in these apps (executable names, lowercase).
    # Empty list = every app. Add/remove in Settings. This is what keeps it
    # from firing in Claude, your terminal, code editors, etc.
    "live_enabled": True,
    "live_apps": [
        "ms-teams.exe", "msteams.exe", "teams.exe",
        "whatsapp.exe", "slack.exe", "discord.exe",
        "telegram.exe", "outlook.exe",
    ],
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(DEFAULTS.copy())
        return DEFAULTS.copy()
    with open(CONFIG_FILE) as f:
        data = json.load(f)
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    return data


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
