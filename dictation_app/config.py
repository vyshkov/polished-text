"""Environment-driven configuration and shared constants."""

import os
import sys
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Ensure Homebrew and standard binary paths are in PATH (crucial for GUI .app launches)
_extra_paths = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin"]
_cur_path = os.environ.get("PATH", "")
for _p in _extra_paths:
    if _p not in _cur_path.split(":") and os.path.exists(_p):
        _cur_path = f"{_p}:{_cur_path}"
os.environ["PATH"] = _cur_path

# Load environment variables from ~/.config/dictation/.env
CONFIG_DIR = Path.home() / ".config" / "dictation"
if load_dotenv:
    load_dotenv(CONFIG_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to `default` (with a warning) if malformed."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        sys.stderr.write(
            f"Config warning: {name}={raw!r} is not a valid integer, using {default}.\n"
        )
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to `default` (with a warning) if malformed."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        sys.stderr.write(
            f"Config warning: {name}={raw!r} is not a valid number, using {default}.\n"
        )
        return default


AUDIO_FILE = Path(tempfile.gettempdir()) / "gemini_dictation_temp.flac"
DEFAULT_AUDIO_DEVICE = os.getenv("AUDIO_DEVICE", "default").strip()
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
DEFAULT_CORRECTOR_MODEL = os.getenv("GEMINI_CORRECTOR_MODEL", "gemini-3.5-flash-lite")
DEFAULT_HOTKEY = os.getenv("HOTKEY", "cmd_r").strip().lower()
PASTE_AUTOMATICALLY = os.getenv("PASTE_AUTOMATICALLY", "true").lower() in ("true", "1", "yes")
REPLACE_SELECTED_TEXT = os.getenv("REPLACE_SELECTED_TEXT", "true").lower() in ("true", "1", "yes")
ENABLE_SOUNDS = os.getenv("ENABLE_SOUNDS", "true").lower() in ("true", "1", "yes")
ENABLE_HUD = os.getenv("ENABLE_HUD", "true").lower() in ("true", "1", "yes")
ENABLE_MENUBAR = os.getenv("ENABLE_MENUBAR", "true").lower() in ("true", "1", "yes")
HISTORY_FILE = CONFIG_DIR / "history.json"
LOG_FILE = CONFIG_DIR / "app.log"
LOG_RETENTION_HOURS = _env_int("LOG_RETENTION_HOURS", 24)
HUD_STYLE = os.getenv("HUD_STYLE", "regular").strip().lower()
# Float the HUD pill next to the text caret (via Accessibility APIs) instead of a fixed
# top-of-screen spot; falls back to the fixed spot if the caret can't be located
HUD_FOLLOW_CARET = os.getenv("HUD_FOLLOW_CARET", "true").lower() in ("true", "1", "yes")
ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() in ("true", "1", "yes")
# Below this RMS amplitude (0.0-1.0 scale) a recording is treated as silence/background noise
SILENCE_RMS_THRESHOLD = _env_float("SILENCE_RMS_THRESHOLD", 0.008)
MIN_SPEECH_DURATION = _env_float("MIN_SPEECH_DURATION", 0.3)
# Raw 16-bit PCM RMS value used as the reference point (before a sqrt/perceptual curve) for a
# "full" HUD equalizer bar; lower it if the bars barely move, raise it if they pin at max
MIC_LEVEL_SCALE = _env_float("MIC_LEVEL_SCALE", 4000)
# Comma-separated languages the model should expect; narrows its search space and avoids
# misidentifying accented speech as an unrelated language
DICTATION_LANGUAGES = [
    lang.strip()
    for lang in os.getenv("DICTATION_LANGUAGES", "English,Ukrainian").split(",")
    if lang.strip()
]
