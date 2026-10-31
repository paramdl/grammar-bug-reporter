import requests
from config import load_config

BASE = "https://api.trello.com/1"


def _auth(config: dict) -> dict:
    return {"key": config["trello_api_key"], "token": config["trello_token"]}


def get_boards() -> list[dict]:
    config = load_config()
    r = requests.get(f"{BASE}/members/me/boards", params={**_auth(config), "filter": "open"})
    r.raise_for_status()
    return [{"id": b["id"], "name": b["name"]} for b in r.json()]


def get_lists(board_id: str) -> list[dict]:
    config = load_config()
    r = requests.get(f"{BASE}/boards/{board_id}/lists", params=_auth(config))
    r.raise_for_status()
    return [{"id": lst["id"], "name": lst["name"]} for lst in r.json()]


def create_bug_card(bug_report: dict) -> dict:
    """Create a Trello card from a bug report dict. Returns card dict with 'url' key."""
    config = load_config()
    if not config.get("trello_list_id"):
        raise ValueError("Trello list not configured. Open Settings > Trello to set it up.")

    severity = bug_report.get("severity", "Medium")
    title = f"[{severity}] {bug_report['title']}"

    steps = "\n".join(
        f"{i + 1}. {s}" for i, s in enumerate(bug_report.get("steps_to_reproduce", []))
    )
    description = (
        f"## Description\n{bug_report.get('description', '')}\n\n"
        f"## Steps to Reproduce\n{steps}\n\n"
        f"## Actual Result\n{bug_report.get('actual_result', '')}\n\n"
        f"## Expected Result\n{bug_report.get('expected_result', '')}\n\n"
        f"## Environment\n{bug_report.get('environment', 'Please fill in')}\n\n"
        f"## Labels\n{', '.join(bug_report.get('labels', []))}"
    )

    r = requests.post(
        f"{BASE}/cards",
        params=_auth(config),
        json={"idList": config["trello_list_id"], "name": title, "desc": description},
    )
    r.raise_for_status()
    card = r.json()
    return {"id": card["id"], "url": card["shortUrl"], "name": card["name"]}
