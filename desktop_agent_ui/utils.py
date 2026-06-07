from pathlib import Path


class QueueWriter:
    """Redirect stdout/stderr into a queue for the GUI log pane."""
    def __init__(self, output_queue):
        self.output_queue = output_queue

    def write(self, text):
        if text:
            self.output_queue.put(text)

    def flush(self):
        pass


def get_effective_scan_paths(desktop_path=""):
    desktop_path = str(desktop_path or "").strip()

    if desktop_path:
        return [Path(desktop_path)]

    paths = [Path.home() / "Desktop"]
    public_desktop = Path(Path.home().anchor) / "Users" / "Public" / "Desktop"

    if public_desktop.exists():
        paths.append(public_desktop)

    unique_paths = []
    seen = set()

    for path in paths:
        try:
            key = str(path.resolve()).lower()
        except Exception:
            key = str(path).lower()

        if key in seen:
            continue

        seen.add(key)
        unique_paths.append(path)

    return unique_paths


def format_scan_paths(paths):
    return " + ".join(str(path) for path in paths)
