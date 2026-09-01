"""Tests for config.py's env-var parsing helpers (malformed .env values must not crash)."""

from dictation_app.config import _env_float, _env_int


def test_env_int_parses_valid_value(monkeypatch):
    monkeypatch.setenv("SOME_INT", "42")
    assert _env_int("SOME_INT", 24) == 42


def test_env_int_falls_back_on_missing_value():
    assert _env_int("MISSING_INT_VAR", 24) == 24


def test_env_int_falls_back_on_malformed_value(monkeypatch, capsys):
    monkeypatch.setenv("SOME_INT", "not-a-number")
    assert _env_int("SOME_INT", 24) == 24
    assert "not a valid integer" in capsys.readouterr().err


def test_env_float_parses_valid_value(monkeypatch):
    monkeypatch.setenv("SOME_FLOAT", "0.05")
    assert _env_float("SOME_FLOAT", 0.008) == 0.05


def test_env_float_falls_back_on_malformed_value(monkeypatch, capsys):
    monkeypatch.setenv("SOME_FLOAT", "abc")
    assert _env_float("SOME_FLOAT", 0.008) == 0.008
    assert "not a valid number" in capsys.readouterr().err
