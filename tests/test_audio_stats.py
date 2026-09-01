"""Tests for sox stat parsing and the has_speech silence heuristic."""

from unittest.mock import patch

from dictation_app.audio import _parse_sox_stats, has_speech

SAMPLE_SOX_STAT_OUTPUT = """
Samples read:              48000
Length (seconds):          3.000000
Scaled by:         2147483647.0
Maximum amplitude:     0.250000
Minimum amplitude:    -0.230000
Midline amplitude:     0.010000
Mean    norm:          0.020000
Mean    amplitude:     0.000100
RMS     amplitude:     0.050000
Rough   frequency:          200
Volume adjustment:        4.000
"""


def test_parse_sox_stats_extracts_known_keys():
    stats = _parse_sox_stats(SAMPLE_SOX_STAT_OUTPUT)
    assert stats["Length (seconds)"] == 3.0
    assert stats["RMS amplitude"] == 0.05
    assert stats["Maximum amplitude"] == 0.25


def test_parse_sox_stats_ignores_unparseable_lines():
    stats = _parse_sox_stats("not a stat line\nLength (seconds):   1.5\n")
    assert stats == {"Length (seconds)": 1.5}


def test_parse_sox_stats_empty_input():
    assert _parse_sox_stats("") == {}


def test_has_speech_true_for_loud_enough_and_long_enough_clip(tmp_path):
    path = tmp_path / "clip.flac"
    path.touch()
    with patch("dictation_app.audio.get_audio_stats") as mock_stats:
        mock_stats.return_value = {"Length (seconds)": 1.0, "RMS amplitude": 0.05}
        assert has_speech(path) is True


def test_has_speech_false_when_too_short(tmp_path):
    path = tmp_path / "clip.flac"
    with patch("dictation_app.audio.get_audio_stats") as mock_stats:
        mock_stats.return_value = {"Length (seconds)": 0.05, "RMS amplitude": 0.05}
        assert has_speech(path) is False


def test_has_speech_false_when_too_quiet(tmp_path):
    path = tmp_path / "clip.flac"
    with patch("dictation_app.audio.get_audio_stats") as mock_stats:
        mock_stats.return_value = {"Length (seconds)": 1.0, "RMS amplitude": 0.0001}
        assert has_speech(path) is False
