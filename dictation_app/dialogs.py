"""Native macOS dialog pop-ups for Gemini rate limits and user interactions."""

import subprocess

try:
    import AppKit

    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False

from .config import AVAILABLE_MODELS, get_model_display_name
from .logger import get_logger

logger = get_logger("Dialogs")


def _escape_applescript(s: str) -> str:
    """Escape text for safe interpolation inside AppleScript double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def get_frontmost_app():
    """Capture reference to the currently frontmost active application."""
    if HAS_APPKIT:
        try:
            return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        except Exception:
            pass
    return None


def reactivate_app(app):
    """Reactivate a previously active application to restore user focus."""
    if app is not None and HAS_APPKIT:
        try:
            app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        except Exception:
            pass


def get_fallback_models(
    current_model: str,
    tried_models: set[str] | None = None,
    available_models: list[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    """Return available fallback models in priority order, excluding current and tried ones."""
    models = available_models if available_models is not None else AVAILABLE_MODELS
    tried = set(tried_models or [])
    tried.add(current_model)
    return [(mid, name) for mid, name in models if mid not in tried]


def prompt_model_switch_on_rate_limit(
    current_model: str,
    tried_models: set[str] | None = None,
    available_models: list[tuple[str, str]] | None = None,
    timeout: float = 120.0,
) -> str | None:
    """Display a native macOS dialog proposing to switch to another model and retry transcription.

    Returns the new model_id if accepted, or None if the user cancelled or no models remain.
    """
    models = available_models if available_models is not None else AVAILABLE_MODELS
    candidates = get_fallback_models(current_model, tried_models, models)

    if not candidates:
        logger.warning("No alternative models available to switch to on rate limit.")
        _show_all_exhausted_dialog(timeout=timeout)
        return None

    suggested_id, suggested_display = candidates[0]
    current_display = get_model_display_name(current_model, models)

    frontmost_app = get_frontmost_app()

    curr_escaped = _escape_applescript(current_display)
    sugg_escaped = _escape_applescript(suggested_display)

    prompt_text = (
        f"The Gemini rate limit was reached for {curr_escaped}.\\n\\n"
        f"Would you like to switch to {sugg_escaped} and retry with the same recording?"
    )

    has_other_options = len(candidates) > 1
    buttons_expr = (
        '{"Cancel", "Other Models...", "Switch & Retry"}'
        if has_other_options
        else '{"Cancel", "Switch & Retry"}'
    )

    script = f"""
    try
        tell application "System Events"
            activate
            set theResult to display dialog "{prompt_text}" buttons {buttons_expr} default button "Switch & Retry" cancel button "Cancel" with title "Gemini Dictation - Rate Limit" with icon caution
            return button returned of theResult
        end tell
    on error errMsg number errNum
        if errNum is -128 then
            return "CANCEL"
        end if
        try
            set theResult to display dialog "{prompt_text}" buttons {buttons_expr} default button "Switch & Retry" cancel button "Cancel" with title "Gemini Dictation - Rate Limit" with icon caution
            return button returned of theResult
        on error
            return "CANCEL"
        end try
    end try
    """

    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except Exception as e:
        logger.error("Failed to display rate limit dialog: %s", e)
        return None

    if proc.returncode != 0:
        logger.info("User cancelled rate limit dialog")
        return None

    button_clicked = proc.stdout.strip()

    if button_clicked == "Switch & Retry":
        selected_model = suggested_id
    elif button_clicked == "Other Models...":
        selected_model = _prompt_model_picker(candidates, suggested_display, timeout=timeout)
    else:
        logger.info("User dismissed or cancelled dialog (result=%r)", button_clicked)
        return None

    if selected_model:
        reactivate_app(frontmost_app)
        return selected_model

    return None


def _prompt_model_picker(
    candidates: list[tuple[str, str]],
    default_display: str,
    timeout: float = 120.0,
) -> str | None:
    """Show a list picker allowing the user to choose an alternative Gemini model."""
    quoted_names = [f'"{_escape_applescript(name)}"' for _, name in candidates]
    names_list_str = "{" + ", ".join(quoted_names) + "}"
    default_escaped = _escape_applescript(default_display)

    script = f"""
    try
        tell application "System Events"
            activate
            set choiceList to {names_list_str}
            set chosen to choose from list choiceList with prompt "Select a Gemini model to retry with:" with title "Gemini Dictation - Select Model" default items {{"{default_escaped}"}} OK button name "Switch & Retry" cancel button name "Cancel"
            if chosen is false then
                return "CANCEL"
            else
                return item 1 of chosen
            end if
        end tell
    on error
        return "CANCEL"
    end try
    """

    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except Exception as e:
        logger.error("Failed to display model picker dialog: %s", e)
        return None

    if proc.returncode != 0:
        return None

    chosen_name = proc.stdout.strip()
    if not chosen_name or chosen_name == "CANCEL":
        return None

    for mid, name in candidates:
        if name == chosen_name or mid == chosen_name:
            return mid

    return None


def _show_all_exhausted_dialog(timeout: float = 30.0):
    """Notify the user that all available models have reached rate limits."""
    script = """
    try
        tell application "System Events"
            activate
            display dialog "All available Gemini models have reached their rate limit quota.\n\nPlease wait a bit before dictating again." buttons {"OK"} default button "OK" with title "Gemini Dictation - Quota Exceeded" with icon stop
        end tell
    on error
        try
            display dialog "All available Gemini models have reached their rate limit quota.\n\nPlease wait a bit before dictating again." buttons {"OK"} default button "OK" with title "Gemini Dictation - Quota Exceeded" with icon stop
        on error
            return
        end try
    end try
    """
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except Exception:
        pass
