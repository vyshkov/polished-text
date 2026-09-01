"""Logging utilities, standardized log formatting, automatic daily rotation, and log lifecycle."""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .config import LOG_FILE, LOG_RETENTION_HOURS

# Shared logging setup flag
_LOGGING_INITIALIZED = False


def setup_logging(log_path: Optional[Path] = None, log_level: int = logging.INFO) -> None:
    """Initialize standard logging configuration with file and console handlers."""
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return

    path = log_path or LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    # Standard log format: 2026-09-01 23:05:12 [INFO] [Engine] Message
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if reloaded
    root_logger.handlers.clear()

    # 1. File Handler (app.log)
    try:
        file_handler = logging.FileHandler(str(path), mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Failed to attach file logger: {e}\n")

    # 2. Console/Terminal Handler (if attached to interactive tty and not redirected)
    if sys.stdout.isatty():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)

    _LOGGING_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """Get or create a named logger conforming to standard formatting."""
    if not _LOGGING_INITIALIZED:
        setup_logging()
    return logging.getLogger(name)


def rotate_and_prune_logs(
    log_path: Optional[Path] = None,
    max_age_hours: Optional[int] = None,
    max_size_bytes: int = 2 * 1024 * 1024,
) -> None:
    """Rotate and prune log files older than max_age_hours or larger than max_size_bytes."""
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
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{ts} [INFO] [Logger] Log auto-rotated: previous log older than {max_hours}h.\n")
            return

        # 2. Trim if file exceeds max size (e.g. 2 MB) - retain last 500 lines
        if stat.st_size > max_size_bytes:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            keep_lines = lines[-500:] if len(lines) > 500 else lines
            with open(path, "w", encoding="utf-8") as f:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{ts} [INFO] [Logger] Log trimmed due to size limit.\n")
                f.writelines(keep_lines)
    except Exception as e:
        sys.stderr.write(f"Log rotation notice: {e}\n")


def clear_log_file(log_path: Optional[Path] = None) -> bool:
    """Cleanly wipe log file."""
    path = log_path or LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{ts} [INFO] [Logger] Log file cleared by user.\n")
        return True
    except Exception as e:
        sys.stderr.write(f"Failed to clear log: {e}\n")
        return False


def open_log_file(log_path: Optional[Path] = None) -> None:
    """Open log file using macOS default app (Console / TextEdit)."""
    path = log_path or LOG_FILE
    try:
        if not path.exists():
            clear_log_file(path)
        subprocess.Popen(["open", str(path)])
    except Exception as e:
        sys.stderr.write(f"Failed to open log file: {e}\n")
