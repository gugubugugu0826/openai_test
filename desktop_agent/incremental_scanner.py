from __future__ import annotations

from pathlib import Path

from desktop_agent.source_manager import Source, get_source_snapshot_path
from desktop_agent.state import now_str
from desktop_agent.storage import load_json, save_json


def load_snapshot(source_id: str) -> dict:
    """Load last-scan snapshot for a source. Returns {str(path): first_seen_at}."""
    snap_path = get_source_snapshot_path(source_id)
    if not snap_path.exists():
        return {}
    try:
        data = load_json(snap_path)
        return data.get("seen", {})
    except Exception:
        return {}


def save_snapshot(source_id: str, items: list[dict]) -> None:
    """Persist the current scan result as a snapshot for future incremental runs."""
    snap_path = get_source_snapshot_path(source_id)
    snap_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_snapshot(source_id)
    now = now_str()

    seen: dict[str, str] = {}
    for item in items:
        path_key = str(item.get("path", ""))
        # Preserve original first_seen_at if the item was already known
        seen[path_key] = existing.get(path_key, now)

    save_json(snap_path, {"updated_at": now, "source_id": source_id, "seen": seen})


def filter_new_items(current_items: list[dict], snapshot: dict) -> list[dict]:
    """Return only items whose path is not in the snapshot (new since last scan)."""
    return [item for item in current_items if str(item.get("path", "")) not in snapshot]


def scan_incremental_or_full(source: Source, all_items: list[dict]) -> list[dict]:
    """
    Given all scanned items for a source, return the subset to process
    based on the source's scan_mode:
      - "full"        → return all items
      - "incremental" → return only new items not seen in the last snapshot
    """
    if source.scan_mode != "incremental":
        return all_items

    snapshot = load_snapshot(source.id)
    if not snapshot:
        return all_items  # First run: treat as full

    return filter_new_items(all_items, snapshot)
