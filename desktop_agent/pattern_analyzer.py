from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from desktop_agent.categories import CATEGORIES
from desktop_agent.i18n import t
from desktop_agent.memory import add_memory_rule, load_memory
from desktop_agent.storage import load_json


HISTORY_DIR = "history"
MIN_CORRECTIONS_THRESHOLD = 2  # How many times a correction must repeat to suggest a rule


@dataclass
class RuleSuggestion:
    match: str
    from_category: str
    to_category: str
    count: int
    suggestion_text: str

    def as_dict(self) -> dict:
        return {
            "match": self.match,
            "from_category": self.from_category,
            "to_category": self.to_category,
            "count": self.count,
            "suggestion_text": self.suggestion_text,
        }


def _load_history_reviews() -> list[dict]:
    """Load all archived review JSON files from history/."""
    hist_dir = Path(HISTORY_DIR)
    if not hist_dir.exists():
        return []
    reviews = []
    for path in sorted(hist_dir.glob("review_*.json"), key=lambda p: p.stat().st_mtime):
        try:
            data = load_json(path)
            reviews.append(data)
        except Exception:
            continue
    return reviews


def _already_in_memory(match: str, to_category: str) -> bool:
    memory = load_memory()
    for rule in memory.get("rules", []):
        if (
            rule.get("match", "").lower() == match.lower()
            and rule.get("category", "").lower() == to_category.lower()
        ):
            return True
    return False


def analyze_correction_history() -> list[RuleSuggestion]:
    """
    Scan history review files, find patterns where the user repeatedly
    corrected the same item from one category to another.
    Returns suggested rules that are NOT yet in memory.
    """
    reviews = _load_history_reviews()
    if not reviews:
        return []

    # Key: (match_text_lower, from_category, to_category) → count
    correction_counter: Counter = Counter()
    # Track the canonical (non-lowered) match text
    match_display: dict[str, str] = {}

    for review in reviews:
        for item in review.get("items", []):
            if not item.get("enabled", True):
                continue
            name = item.get("name", "")
            ai_cat = item.get("ai_category", "")
            human_cat = item.get("human_category", "")

            if not name or not ai_cat or not human_cat:
                continue
            if ai_cat == human_cat:
                continue
            if human_cat not in CATEGORIES:
                continue

            match_text = Path(name).stem
            if len(match_text.strip()) < 3:
                continue

            key = (match_text.lower(), ai_cat, human_cat)
            correction_counter[key] += 1
            match_display[match_text.lower()] = match_text

    suggestions: list[RuleSuggestion] = []
    for (match_lower, from_cat, to_cat), count in correction_counter.items():
        if count < MIN_CORRECTIONS_THRESHOLD:
            continue
        if _already_in_memory(match_lower, to_cat):
            continue

        match = match_display.get(match_lower, match_lower)
        text = t(
            "pattern.suggestion_text",
            match=match,
            from_cat=from_cat,
            to_cat=to_cat,
            count=count,
            default=f"我注意到你 {count} 次把含\"{match}\"的文件从「{from_cat}」改为「{to_cat}」，建议添加为规则",
        )
        suggestions.append(RuleSuggestion(
            match=match,
            from_category=from_cat,
            to_category=to_cat,
            count=count,
            suggestion_text=text,
        ))

    # Sort by count descending (most repeated first)
    suggestions.sort(key=lambda s: s.count, reverse=True)
    return suggestions


def accept_suggestion(suggestion: RuleSuggestion) -> bool:
    """Write a suggested rule into agent_memory.json. Returns True if added."""
    note = t(
        "pattern.rule_note",
        count=suggestion.count,
        from_cat=suggestion.from_category,
        default=f"自动从行为历史学习（纠错 {suggestion.count} 次，原分类：{suggestion.from_category}）",
    )
    return add_memory_rule(suggestion.match, suggestion.to_category, note=note)


def show_suggestions() -> None:
    """CLI display of pattern-based rule suggestions."""
    suggestions = analyze_correction_history()
    print("=" * 80)
    print(t("pattern.header", default="行为模式分析 — 规则建议"))
    print("=" * 80)

    if not suggestions:
        print(t("pattern.no_suggestions", default="暂无新的规则建议（需要 2 次以上的一致性纠错）"))
        return

    for i, sug in enumerate(suggestions, start=1):
        print(f"{i}. {sug.suggestion_text}")
        print(f"   match={sug.match}  {sug.from_category} → {sug.to_category}  (×{sug.count})")
        print()
