# Grammar & Bug Reporter

A Windows tray app that fixes grammar anywhere you type and turns rough notes into structured bug reports,
built to speed up day-to-day QA writing.

| Hotkey | What it does |
|---|---|
| `Ctrl+Alt+G` | Grabs the selected text in any app, shows a corrected version (with tone options) and pastes it back |
| `Ctrl+Alt+B` | Opens the bug reporter: paste notes or a description, get title, steps to reproduce, expected/actual and severity, then send it to a Trello list as a card |
| Live check | Optional inline suggestions while you type, limited to the apps you choose (Teams, Slack, Outlook… by default) |

**Stack:** Python, CustomTkinter, pystray, UI Automation (selected text), Google Gemini API (JSON-mode prompts with retry/back-off on 429), Trello REST API.

## Setup
```bat
install.bat
```
Then set your keys as environment variables (or in Settings, stored in `%USERPROFILE%\.grammar_tool\config.json`, never in the repo):

| Variable | Used for |
|---|---|
| `GOOGLE_API_KEY` | Gemini (Google AI Studio key) |
| `TRELLO_API_KEY`, `TRELLO_TOKEN` | Creating cards |
| `TRELLO_BOARD_ID` | Default board (list is picked in Settings) |

Run with `Start_GrammarTool.bat`.

## Layout
```
main.py             tray icon, global hotkeys, worker queue
grammar_checker.py  read selection, paste corrected text
live_checker.py     opt-in inline checking per app
ai_client.py        Gemini client, JSON prompts, quota handling
trello_client.py    bug report → Trello card
ui/                 overlay, live suggestion, bug report and settings windows
```
