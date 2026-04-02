"""
item_catalog.py — Loads item definitions from data/items/*.json at import time.

Each JSON file in data/items/ describes one item.  The catalog is built once
on first import and cached in ITEM_CATALOG (dict keyed by item_id).

To add a new item, drop a new .json file in data/items/ — no Python changes needed.
"""

import json
import pathlib
from typing import Optional

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data" / "items"

# Built once at import time: item_id -> item dict
ITEM_CATALOG: dict[str, dict] = {}

for _path in sorted(_DATA_DIR.glob("*.json")):
    _item = json.loads(_path.read_text(encoding="utf-8"))
    ITEM_CATALOG[_item["item_id"]] = _item


def get_item(item_id: str) -> Optional[dict]:
    """Return the item definition dict for item_id, or None if not found."""
    return ITEM_CATALOG.get(item_id)


def all_items() -> list:
    """Return all item definitions as a list."""
    return list(ITEM_CATALOG.values())
