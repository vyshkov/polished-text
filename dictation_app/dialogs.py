"""Native macOS dialog pop-ups for Gemini rate limits and user interactions."""

import json
import subprocess
import sys

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
        f"The rate limit quota was reached for {curr_escaped}.\\n\\n"
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
            set chosen to choose from list choiceList with prompt "Select a model to retry with:" with title "Dictation - Select Model" default items {{"{default_escaped}"}} OK button name "Switch & Retry" cancel button name "Cancel"
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
            display dialog "All available dictation models have reached their rate limit quota.\n\nPlease wait a bit before dictating again." buttons {"OK"} default button "OK" with title "Dictation - Quota Exceeded" with icon stop
        end tell
    on error
        try
            display dialog "All available dictation models have reached their rate limit quota.\n\nPlease wait a bit before dictating again." buttons {"OK"} default button "OK" with title "Dictation - Quota Exceeded" with icon stop
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


def prompt_write_dialog(
    clipboard_preview: str | None = None,
    timeout: float = 300.0,
) -> tuple[str, bool] | None:
    """Display a native macOS dialog prompting for text to write and clipboard context.

    Returns: (prompt, include_clipboard) if submitted, or None if cancelled.
    """
    payload = json.dumps({"clipboard_preview": clipboard_preview or ""})
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "dictation_app.dialogs", "write-prompt"],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except Exception as e:
        logger.error("Failed to run write dialog helper: %s", e)
        return _prompt_write_applescript(clipboard_preview, timeout=timeout)

    if proc.returncode != 0:
        return None

    try:
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            return None
        data = json.loads(lines[-1])
        if data.get("status") == "ok":
            prompt_text = data.get("prompt", "").strip()
            if not prompt_text:
                return None
            return prompt_text, bool(data.get("include_clipboard", False))
        return None
    except Exception as e:
        logger.warning("Error parsing write dialog response: %s", e)
        return None


def _prompt_write_applescript(
    clipboard_preview: str | None = None, timeout: float = 120.0
) -> tuple[str, bool] | None:
    """Fallback AppleScript write prompt if native Cocoa helper is unavailable."""
    escaped_title = "Write with Gemini"
    prompt_msg = "Enter instructions for what Gemini should write:"
    has_clip = bool(clipboard_preview and clipboard_preview.strip())

    if has_clip:
        buttons = '{"Cancel", "Write + Context", "Write"}'
        default_btn = '"Write"'
    else:
        buttons = '{"Cancel", "Write"}'
        default_btn = '"Write"'

    script = f"""
    try
        tell application "System Events"
            activate
            set theResult to display dialog "{prompt_msg}" default answer "" buttons {buttons} default button {default_btn} cancel button "Cancel" with title "{escaped_title}"
            return (button returned of theResult) & "\\n" & (text returned of theResult)
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
        if proc.returncode != 0 or not proc.stdout.strip() or proc.stdout.strip() == "CANCEL":
            return None
        parts = proc.stdout.split("\n", 1)
        btn = parts[0].strip()
        text = parts[1].strip() if len(parts) > 1 else ""
        if not text:
            return None
        return text, (btn == "Write + Context")
    except Exception as e:
        logger.error("AppleScript write fallback failed: %s", e)
        return None


def _run_write_prompt_cocoa():
    """Standalone process entrypoint displaying native Cocoa NSAlert with input field & checkbox."""
    clipboard_preview = None
    try:
        raw_in = sys.stdin.read()
        if raw_in:
            data = json.loads(raw_in)
            clipboard_preview = data.get("clipboard_preview")
    except Exception:
        pass

    if not HAS_APPKIT:
        res = _prompt_write_applescript(clipboard_preview)
        if res:
            print(json.dumps({"status": "ok", "prompt": res[0], "include_clipboard": res[1]}))
        else:
            print(json.dumps({"status": "cancelled"}))
        return

    try:
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Write with Gemini")
        alert.setInformativeText_("Enter instructions or a prompt for what you want to write:")
        alert.addButtonWithTitle_("OK")
        alert.addButtonWithTitle_("Cancel")

        box_width = 440
        box_height = 80
        view = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, box_width, box_height))

        tf = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(0, 28, box_width, 48))
        tf.cell().setWraps_(True)
        tf.cell().setScrollable_(False)
        tf.setPlaceholderString_("e.g. Draft a concise follow-up email...")
        tf.setFont_(AppKit.NSFont.systemFontOfSize_(13.0))

        btn_ok = alert.buttons()[0]
        tf.setTarget_(btn_ok)
        tf.setAction_("performClick:")
        view.addSubview_(tf)

        cb = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(0, 2, box_width, 22))
        cb.setButtonType_(AppKit.NSButtonTypeSwitch)
        cb.setFont_(AppKit.NSFont.systemFontOfSize_(12.0))

        if clipboard_preview and clipboard_preview.strip():
            clean_preview = clipboard_preview.strip().replace("\n", " ")
            if len(clean_preview) > 35:
                clean_preview = clean_preview[:35] + "…"
            cb.setTitle_(f'Include clipboard content as context ("{clean_preview}")')
            cb.setEnabled_(True)
            cb.setState_(AppKit.NSControlStateValueOff)
        else:
            cb.setTitle_("Include clipboard content as context (clipboard empty)")
            cb.setEnabled_(False)
            cb.setState_(AppKit.NSControlStateValueOff)

        view.addSubview_(cb)
        alert.setAccessoryView_(view)
        alert.window().setInitialFirstResponder_(tf)

        app.activateIgnoringOtherApps_(True)
        alert.window().makeKeyAndOrderFront_(None)

        res = alert.runModal()
        if res == AppKit.NSAlertFirstButtonReturn:
            prompt_val = str(tf.stringValue() or "").strip()
            inc_clip = bool(cb.state() == AppKit.NSControlStateValueOn)
            print(json.dumps({"status": "ok", "prompt": prompt_val, "include_clipboard": inc_clip}))
        else:
            print(json.dumps({"status": "cancelled"}))
    except Exception as e:
        logger.error("Cocoa write prompt error: %s", e)
        print(json.dumps({"status": "error", "error": str(e)}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "write-prompt":
        _run_write_prompt_cocoa()
