"""Pure state machine for Right Command (⌘) tap/hold/combo detection.

Extracted out of `engine.py` so the tricky timing/state logic (tap to toggle
recording, hold for push-to-talk, Right Command + Option for text correction)
can be unit tested without pynput, the microphone, or the HUD. All side
effects (starting/stopping recording, showing the HUD, calling Gemini) stay
in the caller; this class only tracks key state and returns the action to take.
"""

import time
from enum import Enum, auto


class ComboAction(Enum):
    NONE = auto()
    START_RECORDING = auto()
    STOP_AND_TRANSCRIBE = auto()
    TRIGGER_CORRECTION = auto()
    CANCEL_FALSE_TRIGGER = auto()


class RightCmdComboTracker:
    """Tracks Right Command / Right Command + Option key state and timing."""

    HOLD_THRESHOLD = 0.5
    FALSE_TRIGGER_WINDOW = 0.4

    def __init__(self, clock=time.time):
        self._clock = clock
        self.is_holding = False
        self.is_alt_pressed = False
        self.combo_detected = False
        self.key_press_time = 0.0

    def on_alt_press(self) -> ComboAction:
        self.is_alt_pressed = True
        if self.is_holding:
            # Right Command was already held -> Option pressed second -> combo
            self.combo_detected = True
            return ComboAction.TRIGGER_CORRECTION
        return ComboAction.NONE

    def on_alt_release(self) -> ComboAction:
        self.is_alt_pressed = False
        return ComboAction.NONE

    def on_cmd_r_press(self, is_recording: bool) -> ComboAction:
        if self.is_alt_pressed:
            # Option was already held -> Right Command pressed second -> combo
            self.combo_detected = True
            self.is_holding = True
            self.key_press_time = self._clock()
            return ComboAction.TRIGGER_CORRECTION

        if not self.is_holding:
            self.is_holding = True
            self.key_press_time = self._clock()
            self.combo_detected = False
            return ComboAction.STOP_AND_TRANSCRIBE if is_recording else ComboAction.START_RECORDING

        return ComboAction.NONE

    def on_cmd_r_release(self, is_recording: bool) -> ComboAction:
        held_duration = self._clock() - self.key_press_time
        self.is_holding = False

        if self.combo_detected:
            self.combo_detected = False
            return ComboAction.NONE

        # Held >= threshold behaves as push-to-talk (stop on release); a short
        # tap leaves recording running until the next tap.
        if held_duration >= self.HOLD_THRESHOLD and is_recording:
            return ComboAction.STOP_AND_TRANSCRIBE
        return ComboAction.NONE

    def on_other_key_press(self, is_recording: bool) -> ComboAction:
        """Any non-Option, non-Right-Command key pressed while Right Command is held."""
        if not self.is_holding:
            return ComboAction.NONE
        self.combo_detected = True
        if is_recording and (self._clock() - self.key_press_time < self.FALSE_TRIGGER_WINDOW):
            return ComboAction.CANCEL_FALSE_TRIGGER
        return ComboAction.NONE
