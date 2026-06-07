from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from desktop_agent.i18n import t
from desktop_agent.state import now_str
from desktop_agent.storage import load_json, save_json


QUEUE_FILE = "suggestion_queue.json"


@dataclass
class SuggestionItem:
    source_id: str
    path: str
    name: str
    suggested_category: str
    confidence: str      # "high" | "medium" | "low"
    reason: str
    scanned_at: str
    enabled: bool = True
    human_category: str = ""  # set when user overrides

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SuggestionQueue:
    accumulated_since: str = ""
    pending_count: int = 0
    items: list[SuggestionItem] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "accumulated_since": self.accumulated_since,
            "pending_count": self.pending_count,
            "items": [i.as_dict() for i in self.items],
        }


def _item_from_dict(d: dict) -> SuggestionItem:
    return SuggestionItem(
        source_id=d.get("source_id", "desktop"),
        path=d.get("path", ""),
        name=d.get("name", ""),
        suggested_category=d.get("suggested_category", "无法判断"),
        confidence=d.get("confidence", "medium"),
        reason=d.get("reason", ""),
        scanned_at=d.get("scanned_at", ""),
        enabled=bool(d.get("enabled", True)),
        human_category=d.get("human_category", ""),
    )


def load_queue() -> SuggestionQueue:
    path = Path(QUEUE_FILE)
    if not path.exists():
        return SuggestionQueue(accumulated_since=now_str())
    try:
        data = load_json(path)
        items = [_item_from_dict(i) for i in data.get("items", [])]
        return SuggestionQueue(
            accumulated_since=data.get("accumulated_since", now_str()),
            pending_count=data.get("pending_count", len(items)),
            items=items,
        )
    except Exception:
        return SuggestionQueue(accumulated_since=now_str())


def save_queue(queue: SuggestionQueue) -> None:
    queue.pending_count = sum(1 for i in queue.items if i.enabled)
    save_json(QUEUE_FILE, queue.as_dict())


def append_suggestions(new_items: list[SuggestionItem]) -> SuggestionQueue:
    """Add items to the queue, skipping paths already present."""
    queue = load_queue()
    if not queue.accumulated_since:
        queue.accumulated_since = now_str()

    existing_paths = {i.path for i in queue.items}
    added = 0
    for item in new_items:
        if item.path not in existing_paths:
            queue.items.append(item)
            existing_paths.add(item.path)
            added += 1

    save_queue(queue)
    return queue


def validate_queue() -> SuggestionQueue:
    """Remove items whose source file no longer exists. Silent — no errors."""
    queue = load_queue()
    valid_items = []
    for item in queue.items:
        try:
            if Path(item.path).exists():
                valid_items.append(item)
        except Exception:
            pass
    queue.items = valid_items
    save_queue(queue)
    return queue


def get_pending_count() -> int:
    path = Path(QUEUE_FILE)
    if not path.exists():
        return 0
    try:
        data = load_json(path)
        items = data.get("items", [])
        return sum(1 for i in items if i.get("enabled", True))
    except Exception:
        return 0


def clear_queue() -> None:
    path = Path(QUEUE_FILE)
    if path.exists():
        path.unlink()


def plan_items_from_queue(selected_paths: list[str] | None = None) -> list[dict]:
    """
    Convert confirmed suggestion items to the plan-item format expected by executor.
    If selected_paths is None, use all enabled items.
    """
    queue = validate_queue()
    result = []
    for item in queue.items:
        if not item.enabled:
            continue
        if selected_paths is not None and item.path not in selected_paths:
            continue
        category = item.human_category or item.suggested_category
        result.append(
            {
                "path": item.path,
                "name": item.name,
                "type": _guess_type(item.path, item.name),
                "category": category,
                "human_category": category,
                "reason": item.reason,
                "source_id": item.source_id,
                "classified_by": "suggestion_confirmed",
            }
        )
    return result


def _guess_type(path: str, name: str) -> str:
    p = Path(path)
    if p.is_dir():
        return "folder"
    suffix = p.suffix.lower()
    if suffix in {".lnk", ".url"}:
        return "shortcut"
    return "file"


def show_queue() -> None:
    queue = load_queue()
    print("=" * 80)
    print(t("suggestion.queue_header", default="建议队列"))
    print("=" * 80)

    enabled = [i for i in queue.items if i.enabled]
    if not enabled:
        print(t("suggestion.queue_empty", default="队列为空，没有待处理建议"))
        return

    print(t("suggestion.queue_since", since=queue.accumulated_since, count=len(enabled), default=f"累积自 {queue.accumulated_since}，共 {len(enabled)} 条建议"))
    print("")

    by_source: dict[str, list[SuggestionItem]] = {}
    for item in enabled:
        by_source.setdefault(item.source_id, []).append(item)

    for source_id, items in by_source.items():
        print(f"  [{source_id}] {len(items)} 条")
        for i in items:
            cat = i.human_category or i.suggested_category
            print(f"    {i.name} → {cat} [{i.confidence}]")
        print("")
