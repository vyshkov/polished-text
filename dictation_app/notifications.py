"""macOS system notification banners (Notification Center)."""

import subprocess

from .config import ENABLE_NOTIFICATIONS


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, message: str, subtitle: str = None):
    """Show a native macOS notification banner; it disappears on its own after a few seconds."""
    if not ENABLE_NOTIFICATIONS:
        return
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    if subtitle:
        script += f' subtitle "{_escape(subtitle)}"'
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
