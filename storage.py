import json
import os
from pathlib import Path
from config import DATA_DIR

CONFIG_PATH = Path(DATA_DIR) / "config.json"

DEFAULT_EVENTS = {
    "fills": True,
    "liquidations": True,
    "funding": True,
    "transfers": True,
}


def _load() -> dict:
    if not CONFIG_PATH.exists():
        return {"wallets": {}}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _save(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_wallets() -> dict:
    return _load()["wallets"]


def add_wallet(address: str) -> bool:
    address = address.lower()
    data = _load()
    if address in data["wallets"]:
        return False
    data["wallets"][address] = {
        "label": None,
        "events": {**DEFAULT_EVENTS},
    }
    _save(data)
    return True


def remove_wallet(address: str) -> bool:
    address = address.lower()
    data = _load()
    if address not in data["wallets"]:
        return False
    del data["wallets"][address]
    _save(data)
    return True


def get_events(address: str) -> dict | None:
    address = address.lower()
    wallets = get_wallets()
    if address not in wallets:
        return None
    return wallets[address]["events"]


def toggle_event(address: str, event_type: str) -> bool | None:
    address = address.lower()
    data = _load()
    wallet = data["wallets"].get(address)
    if not wallet or event_type not in wallet["events"]:
        return None
    wallet["events"][event_type] = not wallet["events"][event_type]
    _save(data)
    return wallet["events"][event_type]


def is_event_enabled(address: str, event_type: str) -> bool:
    events = get_events(address)
    if events is None:
        return False
    return events.get(event_type, False)
