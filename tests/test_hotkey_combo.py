"""Tests for the Right Command tap/hold/combo state machine."""

from dictation_app.hotkey_combo import ComboAction, RightCmdComboTracker


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_tap_starts_recording():
    clock = FakeClock()
    tracker = RightCmdComboTracker(clock=clock)

    assert tracker.on_cmd_r_press(is_recording=False) is ComboAction.START_RECORDING
    clock.advance(0.05)
    assert tracker.on_cmd_r_release(is_recording=True) is ComboAction.NONE


def test_second_tap_stops_and_transcribes():
    clock = FakeClock()
    tracker = RightCmdComboTracker(clock=clock)

    tracker.on_cmd_r_press(is_recording=False)
    clock.advance(0.05)
    tracker.on_cmd_r_release(is_recording=True)

    assert tracker.on_cmd_r_press(is_recording=True) is ComboAction.STOP_AND_TRANSCRIBE


def test_push_to_talk_release_stops_after_hold_threshold():
    clock = FakeClock()
    tracker = RightCmdComboTracker(clock=clock)

    tracker.on_cmd_r_press(is_recording=False)
    clock.advance(RightCmdComboTracker.HOLD_THRESHOLD + 0.1)
    assert tracker.on_cmd_r_release(is_recording=True) is ComboAction.STOP_AND_TRANSCRIBE


def test_cmd_then_alt_triggers_correction():
    clock = FakeClock()
    tracker = RightCmdComboTracker(clock=clock)

    tracker.on_cmd_r_press(is_recording=False)
    assert tracker.on_alt_press() is ComboAction.TRIGGER_CORRECTION
    # Releasing cmd_r after a detected combo should not also stop/transcribe
    assert tracker.on_cmd_r_release(is_recording=False) is ComboAction.NONE


def test_alt_then_cmd_triggers_correction():
    clock = FakeClock()
    tracker = RightCmdComboTracker(clock=clock)

    tracker.on_alt_press()
    assert tracker.on_cmd_r_press(is_recording=False) is ComboAction.TRIGGER_CORRECTION


def test_other_key_within_false_trigger_window_cancels():
    clock = FakeClock()
    tracker = RightCmdComboTracker(clock=clock)

    tracker.on_cmd_r_press(is_recording=False)
    clock.advance(0.1)
    assert tracker.on_other_key_press(is_recording=True) is ComboAction.CANCEL_FALSE_TRIGGER


def test_other_key_outside_false_trigger_window_does_not_cancel():
    clock = FakeClock()
    tracker = RightCmdComboTracker(clock=clock)

    tracker.on_cmd_r_press(is_recording=False)
    clock.advance(RightCmdComboTracker.FALSE_TRIGGER_WINDOW + 0.1)
    assert tracker.on_other_key_press(is_recording=True) is ComboAction.NONE


def test_other_key_ignored_when_not_holding():
    tracker = RightCmdComboTracker()
    assert tracker.on_other_key_press(is_recording=False) is ComboAction.NONE
