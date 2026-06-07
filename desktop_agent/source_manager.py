from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from desktop_agent.config import load_config
from desktop_agent.i18n import t
from desktop_agent.storage import save_json


SNAPSHOTS_DIR = "snapshots"

_DANGEROUS_ROOTS = {"C:\\", "D:\\", "E:\\", "F:\\", "G:\\"}


@dataclass
class Source:
    id: str
    label: str
    path: str
    enabled: bool
    scan_mode: str  # "full" | "incremental"
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {
            "id": self.id,
            "label": self.label,
            "path": self.path,
            "enabled": self.enabled,
            "scan_mode": self.scan_mode,
        }
        d.update(self.extra)
        return d

    @property
    def resolved_path(self) -> Path:
        if self.path:
            return Path(self.path)
        if self.id == "desktop":
            return Path.home() / "Desktop"
        if self.id == "downloads":
            return Path.home() / "Downloads"
        if self.id == "documents":
            return Path.home() / "Documents"
        return Path(self.path)


def _source_from_dict(d: dict) -> Source:
    known = {"id", "label", "path", "enabled", "scan_mode"}
    extra = {k: v for k, v in d.items() if k not in known}
    return Source(
        id=d.get("id", "unknown"),
        label=d.get("label", d.get("id", "")),
        path=str(d.get("path") or "").strip(),
        enabled=bool(d.get("enabled", False)),
        scan_mode=str(d.get("scan_mode", "full")),
        extra=extra,
    )


def load_sources(config=None) -> list[Source]:
    cfg = config or load_config()
    raw = cfg.get("sources", [])
    return [_source_from_dict(s) for s in raw]


def get_enabled_sources(config=None) -> list[Source]:
    return [s for s in load_sources(config) if s.enabled]


def validate_source_path(path: str) -> bool:
    """Return True if path exists and is safe to scan."""
    if not path or not path.strip():
        return False
    p = Path(path.strip())
    if not p.exists() or not p.is_dir():
        return False
    try:
        resolved = str(p.resolve())
    except Exception:
        resolved = str(p)
    for root in _DANGEROUS_ROOTS:
        if resolved.rstrip("\\") == root.rstrip("\\"):
            return False
    if len(p.resolve().parts) <= 2:
        return False
    home = str(Path.home().resolve())
    if resolved.rstrip("\\") == home.rstrip("\\"):
        return False
    return True


def get_source_snapshot_path(source_id: str) -> Path:
    return Path(SNAPSHOTS_DIR) / f"{source_id}_snapshot.json"


def save_sources(sources: list[Source], config=None) -> None:
    """Persist sources list back to config.json."""
    from desktop_agent.storage import load_json
    from pathlib import Path as _Path
    cfg_path = _Path("config.json")
    try:
        cfg = load_json(cfg_path)
    except Exception:
        cfg = {}
    cfg["sources"] = [s.as_dict() for s in sources]
    save_json(cfg_path, cfg)


def find_wechat_path() -> str:
    """Try common WeChat file receive locations and return the first found."""
    candidates = [
        Path.home() / "Documents" / "WeChat Files",
        Path("C:/Users") / Path.home().name / "Documents" / "WeChat Files",
        Path("D:/WeChat Files"),
        Path("C:/WeChat Files"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return ""


def show_sources() -> None:
    sources = load_sources()
    print("=" * 80)
    print(t("source_manager.header", default="整理来源配置"))
    print("=" * 80)
    if not sources:
        print(t("source_manager.no_sources", default="未配置任何来源"))
        return
    for s in sources:
        status = t("source_manager.enabled", default="启用") if s.enabled else t("source_manager.disabled", default="禁用")
        path_display = s.resolved_path if s.path else t("source_manager.default_path", default="(默认路径)")
        print(f"[{status}] {s.label} ({s.id}) | {s.scan_mode} | {path_display}")
