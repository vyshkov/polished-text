"""Logging utilities, automatic daily rotation, and log lifecycle management."""

import subprocess
import time
from pathlib import Path
from typing import Optional

from .config import LOG_FILE, LOG_RETENTION_HOURS


def rotate_and_prune_logs(
    log_path: Optional[Path] = None,
    max_age_hours: Optional[int] = None,
    max_size_bytes: int = 2 * 1024 * 1024,
) -> None:
    """Rotate and prune log files older than max_age_hours or larger than max_size_bytes.

    Keeps log footprint small and prevents storing long-term history on disk.
    """
    path = log_path or LOG_FILE
    max_hours = max_age_hours if max_age_hours is not None else LOG_RETENTION_HOURS

    if not path.exists():
        return

    try:
        stat = path.stat()
        now = time.time()
        age_seconds = now - stat.st_mtime

        # 1. Reset if log is older than retention window (e.g. 24 hours)
        if age_seconds > max_hours * 3600:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"=== Log auto-cleaned: previous session was older than {max_hours}h ===\n")
            return

        # 2. Trim if file exceeds max size (e.g., 2 MB) - retain last 500 lines
        if stat.st_size > max_size_bytes:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            keep_lines = lines[-500:] if len(lines) > 500 else lines
            with open(path, "w", encoding="utf-8") as f:
                f.write("=== Log trimmed due to size limit ===\n")
                f.writelines(keep_lines)
    except Exception as e:
        print(f"Log rotation notice: {e}")


def clear_log_file(log_path: Optional[Path] = None) -> bool:
    """Cleanly wipe log file."""
    path = log_path or LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"=== Log cleared at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        return True
    except Exception as e:
        print(f"Failed to clear log: {e}")
        return False


def open_log_file(log_path: Optional[Path] = None) -> None:
    """Open log file using macOS default app (Console / TextEdit)."""
    path = log_path or LOG_FILE
    try:
        if not path.exists():
            clear_log_file(path)
        subprocess.Popen(["open", str(path)])
    except Exception as e:
        print(f"Failed to open log file: {e}")
