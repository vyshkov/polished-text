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
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
DEFAULT_CORRECTOR_MODEL = os.getenv("GEMINI_CORRECTOR_MODEL", "gemini-3.5-flash-lite")

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "").strip()
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus").strip()
AZURE_SPEECH_URL = os.getenv("AZURE_SPEECH_URL", "").strip()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

AVAILABLE_MODELS: list[tuple[str, str]] = [
    ("groq:whisper-large-v3-turbo", "Groq Whisper Large V3 Turbo (Ultra Fast)"),
    ("groq:whisper-large-v3", "Groq Whisper Large V3 (High Accuracy)"),
    ("azure-speech", "Azure Speech (Standard Dictation)"),
    ("gemini-3.8-flash", "Gemini 3.8 Flash (Latest)"),
    ("gemini-3.7-flash", "Gemini 3.7 Flash"),
    ("gemini-3.6-flash", "Gemini 3.6 Flash (Fastest)"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash"),
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite"),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
    ("gemini-flash-latest", "Gemini Flash Latest"),
    ("gemini-flash-lite-latest", "Gemini Flash-Lite Latest"),
    ("gemini-3.5-transcribe", "Gemini 3.5 Transcribe (Audio Optimized)"),
    ("gemini-3-flash-preview", "Gemini 3 Flash Preview"),
]

AVAILABLE_CORRECTOR_MODELS: list[tuple[str, str]] = [
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite (Fastest)"),
    ("gemini-3.6-flash", "Gemini 3.6 Flash"),
    ("gemini-3.8-flash", "Gemini 3.8 Flash (Latest)"),
    ("gemini-3.7-flash", "Gemini 3.7 Flash"),
    ("gemini-3.5-flash", "Gemini 3.5 Flash"),
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
    ("gemini-flash-latest", "Gemini Flash Latest"),
    ("gemini-flash-lite-latest", "Gemini Flash-Lite Latest"),
    ("groq:openai/gpt-oss-120b", "Groq GPT OSS 120B (High Quality)"),
    ("groq:openai/gpt-oss-20b", "Groq GPT OSS 20B (Ultra Fast)"),
    ("groq:qwen/qwen3.8-27b", "Groq Qwen 3.8 27B (Fast)"),
    ("groq:groq/compound", "Groq Compound"),
    ("groq:groq/compound-mini", "Groq Compound Mini"),
]


def get_model_display_name(
    model_id: str,
    models: list[tuple[str, str]] | None = None,
) -> str:
    """Return friendly display name for a model ID, or the model ID itself if unknown."""
    model_list = models if models is not None else AVAILABLE_MODELS
    for mid, name in model_list:
        if mid == model_id:
            return name
    # Also check corrector models if not in the requested list
    if models is None:
        for mid, name in AVAILABLE_CORRECTOR_MODELS:
            if mid == model_id:
                return name
    return model_id


DICTATION_MODEL_METADATA: dict[str, dict[str, str]] = {
    "groq:whisper-large-v3-turbo": {
        "use_case": "Ultra-fast speech dictation (~0.25s)",
        "limits": "Free: 20 RPM, 2k RPD",
    },
    "groq:whisper-large-v3": {
        "use_case": "High-accuracy multilingual dictation",
        "limits": "Free: 20 RPM, 2k RPD",
    },
    "azure-speech": {
        "use_case": "Standard speech dictation",
        "limits": "Free: 5 hrs/mo (F0 tier)",
    },
    "gemini-3.8-flash": {
        "use_case": "Latest multimodal audio understanding",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.7-flash": {
        "use_case": "Fast reasoning & transcription",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.6-flash": {
        "use_case": "Optimized low-latency dictation",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.5-flash": {
        "use_case": "Balanced speed & comprehension",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.5-flash-lite": {
        "use_case": "Fast lightweight speech dictation",
        "limits": "Free: 30 RPM, 1.5k RPD",
    },
    "gemini-3.1-flash-lite": {
        "use_case": "Ultra-lightweight speech dictation",
        "limits": "Free: 30 RPM, 1.5k RPD",
    },
    "gemini-flash-latest": {
        "use_case": "Always newest stable Flash dictation",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-flash-lite-latest": {
        "use_case": "Always newest lightweight Flash dictation",
        "limits": "Free: 30 RPM, 1.5k RPD",
    },
    "gemini-3.5-transcribe": {
        "use_case": "Audio-optimized speech transcription",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3-flash-preview": {
        "use_case": "Preview release of Gemini 3 Flash",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
}

CORRECTOR_MODEL_METADATA: dict[str, dict[str, str]] = {
    "gemini-3.5-flash-lite": {
        "use_case": "Fast grammar, typo fixes & style polish",
        "limits": "Free: 30 RPM, 1.5k RPD",
    },
    "gemini-3.6-flash": {
        "use_case": "High-quality text proofreading & rewrite",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.8-flash": {
        "use_case": "State-of-the-art drafting & editing",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.7-flash": {
        "use_case": "Advanced text reasoning & drafting",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.5-flash": {
        "use_case": "General proofreading & copywriting",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-3.1-flash-lite": {
        "use_case": "Quick corrections & high free quota",
        "limits": "Free: 30 RPM, 1.5k RPD",
    },
    "gemini-flash-latest": {
        "use_case": "Always newest stable Flash for editing",
        "limits": "Free: 15 RPM, 1.5k RPD",
    },
    "gemini-flash-lite-latest": {
        "use_case": "Always newest Flash-Lite for fast polish",
        "limits": "Free: 30 RPM, 1.5k RPD",
    },
    "groq:openai/gpt-oss-120b": {
        "use_case": "Nuanced copy & articulate drafting",
        "limits": "Free: 30 RPM, 1k RPD",
    },
    "groq:openai/gpt-oss-20b": {
        "use_case": "Ultra-fast proofreading (<0.3s)",
        "limits": "Free: 30 RPM, 1k RPD",
    },
    "groq:qwen/qwen3.8-27b": {
        "use_case": "Fast multilingual copy & polish",
        "limits": "Free: 30 RPM, 1k RPD",
    },
    "groq:groq/compound": {
        "use_case": "Compound multi-agent editing & synthesis",
        "limits": "Free: 30 RPM, 1k RPD",
    },
    "groq:groq/compound-mini": {
        "use_case": "Fast compound model for quick polish",
        "limits": "Free: 30 RPM, 1k RPD",
    },
}


def get_model_info(model_id: str, category: str = "dictation") -> dict[str, str]:
    """Return dictionary with 'use_case' and 'limits' for a given model ID and category."""
    lookup = (
        CORRECTOR_MODEL_METADATA
        if category in ("corrector", "polish")
        else DICTATION_MODEL_METADATA
    )
    if model_id in lookup:
        return lookup[model_id]
    alt_lookup = (
        DICTATION_MODEL_METADATA
        if lookup is CORRECTOR_MODEL_METADATA
        else CORRECTOR_MODEL_METADATA
    )
    if model_id in alt_lookup:
        return alt_lookup[model_id]

    if "whisper" in model_id.lower():
        return {"use_case": "Speech-to-text dictation", "limits": "Free: 20 RPM, 2k RPD"}
    if "groq" in model_id.lower():
        return {"use_case": "Fast Groq model", "limits": "Free: 30 RPM, 1k RPD"}
    if "flash-lite" in model_id.lower():
        return {"use_case": "Fast lightweight model", "limits": "Free: 30 RPM, 1.5k RPD"}
    if "gemini" in model_id.lower():
        return {"use_case": "Gemini AI model", "limits": "Free: 15 RPM, 1.5k RPD"}
    return {"use_case": "AI model", "limits": "Free tier available"}


def get_model_subtitle(model_id: str, category: str = "dictation") -> str:
    """Return concise one-line summary for menu items (e.g. 'Use case • Free limits')."""
    info = get_model_info(model_id, category=category)
    return f"{info['use_case']} • {info['limits']}"


def _save_env_var(var_name: str, value: str, env_path: Path | None = None) -> bool:
    """Persist an environment variable key=value to ~/.config/dictation/.env."""
    target_path = env_path or (CONFIG_DIR / ".env")
    try:
        lines = []
        found = False
        prefix_pattern = f"{var_name}="
        export_pattern = f"export {var_name}="
        if target_path.exists():
            with open(target_path, encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith(prefix_pattern) or stripped.startswith(export_pattern):
                        prefix = "export " if stripped.startswith("export ") else ""
                        lines.append(f"{prefix}{var_name}={value}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"{var_name}={value}\n")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        sys.stderr.write(f"Config notice: failed to save {var_name} to {target_path}: {e}\n")
        return False


def save_model_to_env(model_id: str, env_path: Path | None = None) -> bool:
    """Persist the selected dictation model to ~/.config/dictation/.env so it survives restarts."""
    return _save_env_var("GEMINI_MODEL", model_id, env_path=env_path)


def save_corrector_model_to_env(model_id: str, env_path: Path | None = None) -> bool:
    """Persist the selected text corrector model to ~/.config/dictation/.env so it survives restarts."""
    return _save_env_var("GEMINI_CORRECTOR_MODEL", model_id, env_path=env_path)


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

# Common language names mapped to BCP-47 locale tags required by Azure Speech
LANGUAGE_NAME_TO_BCP47: dict[str, str] = {
    "english": "en-US",
    "en": "en-US",
    "ukrainian": "uk-UA",
    "uk": "uk-UA",
    "spanish": "es-ES",
    "es": "es-ES",
    "french": "fr-FR",
    "fr": "fr-FR",
    "german": "de-DE",
    "de": "de-DE",
    "italian": "it-IT",
    "it": "it-IT",
    "polish": "pl-PL",
    "pl": "pl-PL",
    "portuguese": "pt-PT",
    "pt": "pt-PT",
    "japanese": "ja-JP",
    "ja": "ja-JP",
    "chinese": "zh-CN",
    "zh": "zh-CN",
    "korean": "ko-KR",
    "ko": "ko-KR",
    "dutch": "nl-NL",
    "nl": "nl-NL",
    "russian": "ru-RU",
    "ru": "ru-RU",
    "turkish": "tr-TR",
    "tr": "tr-TR",
    "swedish": "sv-SE",
    "sv": "sv-SE",
    "czech": "cs-CZ",
    "cs": "cs-CZ",
    "hindi": "hi-IN",
    "hi": "hi-IN",
}


def resolve_azure_language_tags(languages: list[str] | None = None) -> list[str]:
    """Convert language names or codes to Azure-compatible BCP-47 locale tags (e.g. 'en-US')."""
    raw_langs = languages if languages is not None else DICTATION_LANGUAGES
    tags: list[str] = []
    for lang in raw_langs:
        cleaned = lang.strip()
        lowered = cleaned.lower()
        if lowered in LANGUAGE_NAME_TO_BCP47:
            tag = LANGUAGE_NAME_TO_BCP47[lowered]
        elif "-" in cleaned:
            # Already formatted like 'en-US' or 'uk-UA'
            tag = cleaned
        else:
            tag = cleaned
        if tag and tag not in tags:
            tags.append(tag)
    return tags or ["en-US"]
