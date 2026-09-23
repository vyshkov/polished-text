"""Native macOS dialog pop-ups for Gemini rate limits and user interactions."""

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

try:
    import AppKit
    import objc

    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False

from .config import AVAILABLE_MODELS, DEFAULT_MODEL, get_model_display_name
from .logger import get_logger

logger = get_logger("Dialogs")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VENV_PYTHON = _PROJECT_ROOT / "venv" / "bin" / "python"


def _get_dialog_cmd_and_env(subcommand: str) -> tuple[list[str], dict[str, str], str]:
    """Get the command, environment, and working directory to reliably run a dialog helper."""
    py_exec = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    root_str = str(_PROJECT_ROOT)
    env["PYTHONPATH"] = f"{root_str}:{pythonpath}" if pythonpath else root_str
    return [py_exec, "-m", "dictation_app.dialogs", subcommand], env, root_str


def _make_sf_symbol(name: str):
    """Load a native Apple SF Symbol template image for Cocoa controls."""
    if not HAS_APPKIT:
        return None
    try:
        img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
        if img:
            img.setTemplate_(True)
        return img
    except Exception:
        return None


if HAS_APPKIT:

    class _WriteDialogController(AppKit.NSObject):
        """Controller managing voice recording and transcription inside the Write dialog."""

        def init(self):
            self = objc.super(_WriteDialogController, self).init()
            self.tf = None
            self.btn_mic = None
            self.btn_ok = None
            self.status_label = None
            self.window = None
            self.model = DEFAULT_MODEL
            self.recorder = None
            self.is_recording = False
            self.temp_audio_path = (
                Path(tempfile.gettempdir()) / f"gemini_write_prompt_{os.getpid()}.flac"
            )
            return self

        @objc.python_method
        def setup(self, tf, btn_mic, btn_ok, status_label, window, model: str | None = None):
            self.tf = tf
            self.btn_mic = btn_mic
            self.btn_ok = btn_ok
            self.status_label = status_label
            self.window = window
            self.model = model or DEFAULT_MODEL

        def toggleVoiceRecord_(self, sender):
            if not self.is_recording:
                self.startRecording()
            else:
                self.stopRecording()

        @objc.python_method
        def startRecording(self):
            try:
                from .audio import AudioRecorder

                self.recorder = AudioRecorder(output_path=self.temp_audio_path)
                self.recorder.start()
                self.is_recording = True

                stop_img = _make_sf_symbol("stop.fill") or _make_sf_symbol("stop.circle.fill")
                if stop_img and self.btn_mic:
                    self.btn_mic.setImage_(stop_img)
                    self.btn_mic.setTitle_("")
                elif self.btn_mic:
                    self.btn_mic.setTitle_("⏹️ Stop")

                if self.btn_mic:
                    self.btn_mic.setToolTip_("Click to stop recording and transcribe")
                if self.status_label:
                    self.status_label.setStringValue_("🔴 Listening... Click ⏹️ to finish.")
                    self.status_label.setTextColor_(AppKit.NSColor.systemRedColor())
                if self.btn_ok:
                    self.btn_ok.setEnabled_(False)
            except Exception as e:
                logger.error("Failed to start voice recording in write dialog: %s", e)
                if self.status_label:
                    self.status_label.setStringValue_(f"⚠️ Microphone error: {e}")
                    self.status_label.setTextColor_(AppKit.NSColor.systemOrangeColor())
                self.is_recording = False

        @objc.python_method
        def stopRecording(self):
            self.is_recording = False
            if self.btn_mic:
                self.btn_mic.setEnabled_(False)
            if self.status_label:
                self.status_label.setStringValue_("⏳ Transcribing speech with Gemini...")
                self.status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())

            audio_file = None
            try:
                if self.recorder:
                    audio_file = self.recorder.stop()
            except Exception as e:
                logger.error("Error stopping recorder in write dialog: %s", e)

            if not audio_file or not audio_file.exists() or audio_file.stat().st_size == 0:
                self._finish_transcription("", None)
                return

            def _transcribe_worker():
                transcribed_text = ""
                error_msg = None
                try:
                    from .transcriber import get_transcriber

                    transcriber = get_transcriber(self.model)
                    transcribed_text = transcriber.transcribe(audio_file)
                except Exception as exc:
                    logger.error("Transcription error in write dialog: %s", exc)
                    error_msg = str(exc)

                AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                    lambda: self._finish_transcription(transcribed_text, error_msg)
                )

            threading.Thread(target=_transcribe_worker, daemon=True).start()

        @objc.python_method
        def _finish_transcription(self, text: str, error: str | None):
            if self.btn_mic:
                self.btn_mic.setEnabled_(True)
                mic_img = _make_sf_symbol("mic.fill") or _make_sf_symbol("mic")
                if mic_img:
                    self.btn_mic.setImage_(mic_img)
                    self.btn_mic.setTitle_("")
                else:
                    self.btn_mic.setTitle_("🎙️")
                self.btn_mic.setToolTip_("Dictate prompt with microphone (preserves clipboard)")

            if self.btn_ok:
                self.btn_ok.setEnabled_(True)

            if error:
                short_err = error.split("\n")[0][:45]
                if self.status_label:
                    self.status_label.setStringValue_(f"⚠️ Transcription error: {short_err}")
                    self.status_label.setTextColor_(AppKit.NSColor.systemRedColor())
            elif text:
                current_val = str(self.tf.stringValue() or "").strip()
                new_val = f"{current_val} {text}".strip() if current_val else text
                self.tf.setStringValue_(new_val)
                if self.status_label:
                    self.status_label.setStringValue_("✨ Speech transcribed (clipboard untouched)")
                    self.status_label.setTextColor_(AppKit.NSColor.systemGreenColor())
                if self.window and self.tf:
                    self.window.makeFirstResponder_(self.tf)
            else:
                if self.status_label:
                    self.status_label.setStringValue_("⚠️ No speech detected")
                    self.status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())

            try:
                if self.temp_audio_path.exists():
                    self.temp_audio_path.unlink()
            except Exception:
                pass

        @objc.python_method
        def cleanup(self):
            if self.is_recording and self.recorder:
                try:
                    self.recorder.cancel()
                except Exception:
                    pass
                self.is_recording = False
            try:
                if self.temp_audio_path.exists():
                    self.temp_audio_path.unlink()
            except Exception:
                pass


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


def prompt_server_error_retry(
    current_model: str,
    error_message: str | None = None,
    tried_models: set[str] | None = None,
    available_models: list[tuple[str, str]] | None = None,
    timeout: float = 120.0,
) -> str | None:
    """Display a native macOS dialog proposing to retry or switch model on 503 server error.

    Returns the model_id to retry with, or None if the user cancelled.
    """
    models = available_models if available_models is not None else AVAILABLE_MODELS
    frontmost_app = get_frontmost_app()

    payload = json.dumps(
        {
            "current_model": current_model,
            "error_message": error_message or "",
            "available_models": models,
        }
    )

    cmd, env, cwd = _get_dialog_cmd_and_env("server-error-prompt")
    try:
        proc = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except Exception as e:
        logger.error("Failed to run server error dialog helper: %s", e)
        return _prompt_server_error_applescript(
            current_model, error_message, models, timeout=timeout
        )

    if proc.returncode != 0:
        logger.warning(
            "Server error dialog helper exited with code %d: stderr=%s, stdout=%s",
            proc.returncode,
            proc.stderr.strip() if proc.stderr else "",
            proc.stdout.strip() if proc.stdout else "",
        )
        return _prompt_server_error_applescript(
            current_model, error_message, models, timeout=timeout
        )

    try:
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            return None
        data = json.loads(lines[-1])
        if data.get("status") == "retry":
            selected_model = data.get("model") or current_model
            reactivate_app(frontmost_app)
            return selected_model
        return None
    except Exception as e:
        logger.warning("Error parsing server error dialog response: %s", e)
        return _prompt_server_error_applescript(
            current_model, error_message, models, timeout=timeout
        )


def _prompt_server_error_applescript(
    current_model: str,
    error_message: str | None = None,
    available_models: list[tuple[str, str]] | None = None,
    timeout: float = 120.0,
) -> str | None:
    """Fallback AppleScript server error dialog if native Cocoa helper is unavailable."""
    models = available_models if available_models is not None else AVAILABLE_MODELS
    current_display = get_model_display_name(current_model, models)
    curr_escaped = _escape_applescript(current_display)

    prompt_text = (
        f"The server responded with error 503 (Service Unavailable) for {curr_escaped}.\\n\\n"
        "Would you like to retry with this model, switch models, or cancel?"
    )

    has_other_options = len(models) > 1
    buttons_expr = (
        '{"Cancel", "Change Model...", "Retry"}' if has_other_options else '{"Cancel", "Retry"}'
    )

    script = f"""
    try
        tell application "System Events"
            activate
            set theResult to display dialog "{prompt_text}" buttons {buttons_expr} default button "Retry" cancel button "Cancel" with title "Gemini Dictation - Server Error (503)" with icon caution
            return button returned of theResult
        end tell
    on error errMsg number errNum
        if errNum is -128 then
            return "CANCEL"
        end if
        try
            set theResult to display dialog "{prompt_text}" buttons {buttons_expr} default button "Retry" cancel button "Cancel" with title "Gemini Dictation - Server Error (503)" with icon caution
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
        logger.error("AppleScript server error prompt failed: %s", e)
        return None

    if proc.returncode != 0:
        return None

    button_clicked = proc.stdout.strip()
    if button_clicked == "Retry":
        return current_model
    elif button_clicked == "Change Model...":
        return _prompt_model_picker(models, current_display, timeout=timeout)
    return None


def prompt_write_dialog(
    clipboard_preview: str | None = None,
    model: str | None = None,
    timeout: float = 300.0,
) -> tuple[str, bool] | None:
    """Display a native macOS dialog prompting for text to write and clipboard context.

    Returns: (prompt, include_clipboard) if submitted, or None if cancelled.
    """
    payload = json.dumps(
        {
            "clipboard_preview": clipboard_preview or "",
            "model": model or DEFAULT_MODEL,
        }
    )
    cmd, env, cwd = _get_dialog_cmd_and_env("write-prompt")
    try:
        proc = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except Exception as e:
        logger.error("Failed to run write dialog helper: %s", e)
        return _prompt_write_applescript(clipboard_preview, timeout=timeout)

    if proc.returncode != 0:
        logger.warning(
            "Write dialog helper exited with code %d: stderr=%s, stdout=%s",
            proc.returncode,
            proc.stderr.strip() if proc.stderr else "",
            proc.stdout.strip() if proc.stdout else "",
        )
        return _prompt_write_applescript(clipboard_preview, timeout=timeout)

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
    on error errMsg number errNum
        if errNum is -128 then
            return "CANCEL"
        end if
        try
            set theResult to display dialog "{prompt_msg}" default answer "" buttons {buttons} default button {default_btn} cancel button "Cancel" with title "{escaped_title}"
            return (button returned of theResult) & "\\n" & (text returned of theResult)
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
    """Standalone process entrypoint displaying native Cocoa NSAlert with input field, mic button & checkbox."""
    clipboard_preview = None
    model_name = DEFAULT_MODEL
    try:
        raw_in = sys.stdin.read()
        if raw_in:
            data = json.loads(raw_in)
            clipboard_preview = data.get("clipboard_preview")
            model_name = data.get("model") or DEFAULT_MODEL
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
        alert.setInformativeText_(
            "Enter instructions or dictate a prompt for what you want to write:"
        )
        alert.addButtonWithTitle_("OK")
        btn_cancel = alert.addButtonWithTitle_("Cancel")
        btn_cancel.setKeyEquivalent_("\x1b")

        box_width = 440
        box_height = 96
        view = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, box_width, box_height))

        # Text field (width: 392, height: 48 at y=44)
        tf = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(0, 44, 392, 48))
        tf.cell().setWraps_(True)
        tf.cell().setScrollable_(False)
        tf.setPlaceholderString_("e.g. Draft a concise follow-up email...")
        tf.setFont_(AppKit.NSFont.systemFontOfSize_(13.0))

        btn_ok = alert.buttons()[0]
        tf.setTarget_(btn_ok)
        tf.setAction_("performClick:")
        view.addSubview_(tf)

        # Microphone dictation button (width: 42, height: 48 at x=398, y=44)
        btn_mic = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(398, 44, 42, 48))
        btn_mic.setBezelStyle_(AppKit.NSBezelStyleRounded)
        mic_img = _make_sf_symbol("mic.fill") or _make_sf_symbol("mic")
        if mic_img:
            btn_mic.setImage_(mic_img)
            btn_mic.setImagePosition_(AppKit.NSImageOnly)
        else:
            btn_mic.setTitle_("🎙️")
        btn_mic.setToolTip_("Dictate prompt with microphone (preserves clipboard)")
        view.addSubview_(btn_mic)

        # Status & feedback label (width: 436, height: 16 at x=2, y=24)
        status_label = AppKit.NSTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(2, 24, box_width - 4, 16)
        )
        status_label.setBezeled_(False)
        status_label.setDrawsBackground_(False)
        status_label.setEditable_(False)
        status_label.setSelectable_(False)
        status_label.setFont_(AppKit.NSFont.systemFontOfSize_(11.0))
        status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        status_label.setStringValue_(
            "💡 Click 🎙️ to dictate instructions without altering clipboard."
        )
        view.addSubview_(status_label)

        # Clipboard context inclusion checkbox (width: 440, height: 18 at x=0, y=2)
        cb = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(0, 2, box_width, 18))
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

        controller = _WriteDialogController.alloc().init()
        controller.setup(
            tf=tf,
            btn_mic=btn_mic,
            btn_ok=btn_ok,
            status_label=status_label,
            window=alert.window(),
            model=model_name,
        )
        btn_mic.setTarget_(controller)
        btn_mic.setAction_("toggleVoiceRecord:")

        alert.window().setLevel_(AppKit.NSFloatingWindowLevel)
        alert.window().center()
        app.activateIgnoringOtherApps_(True)
        alert.window().makeKeyAndOrderFront_(None)
        alert.window().makeFirstResponder_(tf)

        res = alert.runModal()
        controller.cleanup()
        if res == AppKit.NSAlertFirstButtonReturn:
            prompt_val = str(tf.stringValue() or "").strip()
            inc_clip = bool(cb.state() == AppKit.NSControlStateValueOn)
            print(json.dumps({"status": "ok", "prompt": prompt_val, "include_clipboard": inc_clip}))
        else:
            print(json.dumps({"status": "cancelled"}))
    except Exception as e:
        logger.error("Cocoa write prompt error: %s", e)
        print(json.dumps({"status": "error", "error": str(e)}))


def _run_server_error_prompt_cocoa():
    """Standalone process entrypoint displaying native Cocoa NSAlert with model dropdown and Retry/Cancel buttons."""
    current_model = None
    error_message = None
    available_models = AVAILABLE_MODELS
    try:
        raw_in = sys.stdin.read()
        if raw_in:
            data = json.loads(raw_in)
            current_model = data.get("current_model")
            error_message = data.get("error_message")
            if "available_models" in data:
                available_models = [tuple(m) for m in data["available_models"]]
    except Exception:
        pass

    if not HAS_APPKIT:
        res = _prompt_server_error_applescript(current_model, error_message, available_models)
        if res:
            print(json.dumps({"status": "retry", "model": res}))
        else:
            print(json.dumps({"status": "cancelled"}))
        return

    try:
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Server Error (503)")

        curr_display = (
            get_model_display_name(current_model, available_models) if current_model else "Gemini"
        )
        curr_escaped = curr_display.replace("\n", " ")

        info_text = (
            f"The server responded with error 503 (Service Unavailable) for {curr_escaped}.\n\n"
            "You can retry with the current model, select a different model, or cancel."
        )
        alert.setInformativeText_(info_text)
        alert.setAlertStyle_(AppKit.NSAlertStyleWarning)

        # Buttons: Retry (default), Cancel (esc)
        alert.addButtonWithTitle_("Retry")
        btn_cancel = alert.addButtonWithTitle_("Cancel")
        btn_cancel.setKeyEquivalent_("\x1b")

        # Accessory view with Model dropdown (NSPopUpButton)
        box_width = 380
        box_height = 36
        view = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, box_width, box_height))

        label = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(0, 7, 50, 20))
        label.setStringValue_("Model:")
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(AppKit.NSFont.systemFontOfSize_(13.0))
        view.addSubview_(label)

        popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            AppKit.NSMakeRect(55, 4, 320, 26), False
        )

        model_ids = []
        selected_index = 0
        for idx, (mid, display_name) in enumerate(available_models):
            popup.addItemWithTitle_(display_name)
            model_ids.append(mid)
            if mid == current_model:
                selected_index = idx

        if current_model and current_model not in model_ids:
            popup.insertItemWithTitle_atIndex_(curr_display, 0)
            model_ids.insert(0, current_model)
            selected_index = 0

        popup.selectItemAtIndex_(selected_index)
        view.addSubview_(popup)

        alert.setAccessoryView_(view)

        app.activateIgnoringOtherApps_(True)
        alert.window().makeKeyAndOrderFront_(None)

        res = alert.runModal()
        if res == AppKit.NSAlertFirstButtonReturn:
            chosen_idx = popup.indexOfSelectedItem()
            chosen_model_id = (
                model_ids[chosen_idx] if 0 <= chosen_idx < len(model_ids) else (current_model or "")
            )
            print(json.dumps({"status": "retry", "model": chosen_model_id}))
        else:
            print(json.dumps({"status": "cancelled"}))
    except Exception as e:
        logger.error("Cocoa server error prompt error: %s", e)
        res = _prompt_server_error_applescript(current_model, error_message, available_models)
        if res:
            print(json.dumps({"status": "retry", "model": res}))
        else:
            print(json.dumps({"status": "cancelled"}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "write-prompt":
        _run_write_prompt_cocoa()
    elif len(sys.argv) > 1 and sys.argv[1] == "server-error-prompt":
        _run_server_error_prompt_cocoa()
