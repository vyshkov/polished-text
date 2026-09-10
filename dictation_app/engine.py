"""Orchestrates recording -> silence check -> transcription -> paste, and hotkey handling."""

import sys
import threading
import time

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

from .audio import AudioRecorder, has_speech
from .clipboard import (
    copy_to_clipboard,
    get_selected_text_info,
    is_likely_editable_context,
    paste_text,
    replace_selected_text,
)
from .config import (
    AUDIO_FILE,
    DEFAULT_AUDIO_DEVICE,
    DEFAULT_CORRECTOR_MODEL,
    DEFAULT_HOTKEY,
    DEFAULT_MODEL,
    ENABLE_HUD,
    ENABLE_MENUBAR,
    PASTE_AUTOMATICALLY,
    REPLACE_SELECTED_TEXT,
    get_model_display_name,
    save_model_to_env,
)
from .corrector import GeminiCorrector
from .history import HistoryManager
from .hotkey_combo import ComboAction, RightCmdComboTracker
from .hud import DictationHUD, run_console_event_loop
from .logger import get_logger
from .menubar import DictationMenuBar
from .notifications import notify
from .sound import play_sound
from .transcriber import GeminiTranscriber, describe_error

logger = get_logger("Engine")


def _is_alt_key(key) -> bool:
    if keyboard is None:
        return False
    if key in (
        keyboard.Key.alt,
        getattr(keyboard.Key, "alt_l", None),
        getattr(keyboard.Key, "alt_r", None),
        getattr(keyboard.Key, "alt_gr", None),
    ):
        return True
    try:
        k_str = str(key).lower()
        if "alt" in k_str or "option" in k_str:
            return True
    except Exception:
        pass
    return False


def check_and_prompt_accessibility() -> bool:
    """Verify macOS accessibility permissions and trigger system prompt if missing."""
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        if AXIsProcessTrusted():
            return True
        options = {kAXTrustedCheckOptionPrompt: True}
        return bool(AXIsProcessTrustedWithOptions(options))
    except Exception:
        return True


class DictationEngine:
    def __init__(
        self,
        hotkey_str: str = DEFAULT_HOTKEY,
        model: str = DEFAULT_MODEL,
        corrector_model: str = DEFAULT_CORRECTOR_MODEL,
        device_name: str = DEFAULT_AUDIO_DEVICE,
    ):
        self.hud = DictationHUD(enabled=ENABLE_HUD)
        self.history = HistoryManager()
        self.recorder = AudioRecorder(
            AUDIO_FILE,
            on_level=self.hud.update_level,
            device_name=device_name,
        )
        self.hotkey_str = hotkey_str.strip().lower()
        self.model = model
        self.corrector_model = corrector_model
        self.device_name = device_name
        self._transcriber = None
        self._corrector = None
        self.listener = None
        self._is_correcting = False

        self.menubar = DictationMenuBar(
            history=self.history,
            hud=self.hud,
            get_active_device=lambda: self.recorder.active_device_display,
            get_current_model=lambda: self.model,
            on_select_model_callback=self.set_model,
            on_quit_callback=self.stop,
            enabled=ENABLE_MENUBAR,
        )

    def set_model(self, new_model: str):
        """Dynamically switch the speech-to-text model, reinitialize transcriber, and persist."""
        if not new_model:
            return
        old_model = self.model
        if old_model == new_model and self._transcriber is not None:
            return

        self.model = new_model
        self._transcriber = GeminiTranscriber(model=new_model)
        logger.info("Dictation model switched dynamically: %s -> %s", old_model, new_model)

        save_model_to_env(new_model)

        if self.hud and getattr(self.hud, "enabled", False):
            display_name = get_model_display_name(new_model)
            short_name = display_name.split("(")[0].strip()
            self.hud.show_done(f"🤖  {short_name}")

    @property
    def transcriber(self):
        if self._transcriber is None:
            self._transcriber = GeminiTranscriber(model=self.model)
        return self._transcriber

    @property
    def corrector(self):
        if self._corrector is None:
            self._corrector = GeminiCorrector(model=self.corrector_model)
        return self._corrector

    def process_and_transcribe(self):
        try:
            self.hud.show_transcribing()
            audio_file = self.recorder.stop()
            if not audio_file:
                logger.warning("No audio detected or recording too short")
                self.hud.show_cancelled("⚠️  No speech")
                return

            if not has_speech(audio_file):
                logger.info(
                    "Detected silence/background noise only from '%s' — skipping Gemini request",
                    self.recorder.active_device_display,
                )
                self.hud.show_cancelled("🔇  No speech")
                play_sound("Basso")
                return

            logger.info("Transcribing audio with Gemini (%s)...", self.transcriber.model)
            start_t = time.time()
            text = self.transcriber.transcribe(audio_file)
            elapsed = time.time() - start_t

            if text:
                logger.info('Transcribed in %.2fs: "%s"', elapsed, text)
                self.history.add(text, kind="dictation")
                self.menubar.update_menu()
                self.hud.show_done()
                paste_text(text)
                play_sound("Hero")
            else:
                logger.warning("No speech recognized by model")
                self.hud.show_cancelled("⚠️  No speech")
                play_sound("Basso")
        except Exception as e:
            reason = describe_error(e)
            logger.error("Transcription error: %s", reason)
            self.hud.show_cancelled("❌  Error")
            play_sound("Basso")
            notify("Dictation failed", reason, subtitle="Gemini transcription error")

    def correct_selection(self):
        """Retrieve selected text on screen, polish it with Gemini, replace in-place if editable, and log."""
        if self._is_correcting:
            return
        self._is_correcting = True
        try:
            start_t = time.time()
            text, is_editable, focused_elem = get_selected_text_info()
            if not text:
                logger.warning("No text selected on screen to correct")
                self.hud.show_cancelled("⚠️  No selection")
                play_sound("Basso")
                return

            self.hud.show_correcting()
            logger.info(
                "Polishing text with Gemini (%s, %d characters)...", self.corrector.model, len(text)
            )
            logger.debug("Original text: %r", text)

            corrected = self.corrector.correct(text)
            elapsed = time.time() - start_t

            if corrected:
                self.history.add(corrected, kind="correction")
                self.menubar.update_menu()

                can_replace = REPLACE_SELECTED_TEXT and (
                    is_editable or is_likely_editable_context(focused_elem)
                )
                if can_replace:
                    logger.info(
                        'Text corrected in %.2fs [mode=in_place_replace]: "%s"', elapsed, corrected
                    )
                    replace_selected_text(corrected, focused_elem)
                    self.hud.show_done("✨  Replaced")
                else:
                    logger.info(
                        'Text corrected in %.2fs [mode=clipboard_copy]: "%s"', elapsed, corrected
                    )
                    copy_to_clipboard(corrected)
                    self.hud.show_done("✨  Copied")

                play_sound("Hero")
            else:
                logger.warning("Correction returned empty text")
                self.hud.show_cancelled("⚠️  Empty text")
                play_sound("Basso")
        except Exception as e:
            reason = describe_error(e)
            logger.error("Text correction error: %s", reason)
            self.hud.show_cancelled("❌  Error")
            play_sound("Basso")
            notify("Text correction failed", reason, subtitle="Gemini corrector error")
        finally:
            self._is_correcting = False

    def trigger_correction_async(self):
        """Run text correction asynchronously so key listener is not blocked."""
        threading.Thread(target=self.correct_selection, daemon=True).start()

    def toggle_recording(self):
        if not self.recorder.is_recording:
            try:
                self.recorder.start()
                self.hud.show_recording()
            except Exception as e:
                logger.error("Error starting recording: %s", e)
                self.hud.show_cancelled("❌  Mic Error")
                play_sound("Basso")
                notify("Dictation failed", str(e), subtitle="Microphone error")
        else:
            self.process_and_transcribe()

    def run_once_interactive(self):
        """Record on Enter key press for testing in terminal."""
        input("\n👉 Press [ENTER] to start recording...")
        self.recorder.start()
        self.hud.show_recording()
        input("👉 Press [ENTER] to stop recording and transcribe...")
        self.process_and_transcribe()

    def start_listener(self):
        if keyboard is None:
            logger.error("'pynput' is required for hotkey listening.")
            sys.exit(1)

        is_right_cmd = self.hotkey_str in ("cmd_r", "right_cmd", "right_command", "<cmd_r>")

        logger.info(
            "Gemini Assistant started (hotkey=%s, input=%s, dict_model=%s, corr_model=%s, replace=%s, paste=%s)",
            self.hotkey_str,
            self.recorder.active_device_display,
            self.model,
            self.corrector_model,
            REPLACE_SELECTED_TEXT,
            PASTE_AUTOMATICALLY,
        )

        # Check macOS Accessibility permission
        if not check_and_prompt_accessibility():
            logger.warning(
                "macOS Accessibility permission not granted! Please allow Gemini Assistant in System Settings > Privacy & Security > Accessibility."
            )
            notify(
                "Accessibility Permission Required",
                "Please enable Gemini Assistant in System Settings > Privacy & Security > Accessibility",
            )

        if is_right_cmd:
            listener = self._create_right_cmd_listener()
        elif self.hotkey_str.startswith("<") and "+" in self.hotkey_str:
            try:
                hotkeys = {self.hotkey_str: self.toggle_recording}
                listener = keyboard.GlobalHotKeys(hotkeys)
            except Exception as e:
                logger.warning("GlobalHotKeys error: %s, falling back to single-key listener.", e)
                listener = self._create_single_key_listener()
        else:
            listener = self._create_single_key_listener()

        self.listener = listener
        listener.start()

        if self.hud.enabled or self.menubar.enabled:
            try:
                run_console_event_loop()
            except (KeyboardInterrupt, SystemExit):
                pass
            finally:
                self.stop()
        else:
            try:
                listener.join()
            except (KeyboardInterrupt, SystemExit):
                pass
            finally:
                self.stop()

    def stop(self):
        """Cleanly stop keyboard listener and release resources."""
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None

    def _create_right_cmd_listener(self):
        """Dedicated intelligent listener for Right Command and Right Command + Option."""
        tracker = RightCmdComboTracker()

        def handle_action(action: ComboAction):
            if action is ComboAction.START_RECORDING:
                self.recorder.start()
                self.hud.show_recording()
            elif action is ComboAction.STOP_AND_TRANSCRIBE:
                logger.debug("Push-to-talk released")
                self.process_and_transcribe()
            elif action is ComboAction.TRIGGER_CORRECTION:
                if self.recorder.is_recording:
                    self.recorder.cancel()
                    self.hud.hide()
                self.trigger_correction_async()
            elif action is ComboAction.CANCEL_FALSE_TRIGGER:
                self.recorder.cancel()
                self.hud.show_cancelled()

        def on_press(key):
            if _is_alt_key(key):
                handle_action(tracker.on_alt_press())
                return
            if key == keyboard.Key.cmd_r:
                handle_action(tracker.on_cmd_r_press(self.recorder.is_recording))
                return
            handle_action(tracker.on_other_key_press(self.recorder.is_recording))

        def on_release(key):
            if _is_alt_key(key):
                handle_action(tracker.on_alt_release())
                return
            if key == keyboard.Key.cmd_r:
                handle_action(tracker.on_cmd_r_release(self.recorder.is_recording))

        return keyboard.Listener(on_press=on_press, on_release=on_release)

    def _create_single_key_listener(self):
        target = self.hotkey_str.strip("<>").lower()

        def on_press(key):
            try:
                k_name = getattr(key, "name", None) or str(key)
                if k_name.lower() == target:
                    self.toggle_recording()
            except Exception:
                pass

        return keyboard.Listener(on_press=on_press)
