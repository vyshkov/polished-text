"""Tests for HistoryManager persistence and dedup behavior."""

import json

from dictation_app.history import HistoryManager


def test_add_and_get_recent(tmp_path):
    history = HistoryManager(file_path=tmp_path / "history.json", max_items=20)

    history.add("hello world", kind="dictation")
    history.add("fixed sentence", kind="correction")

    recent = history.get_recent(5)
    assert [item["text"] for item in recent] == ["fixed sentence", "hello world"]
    assert recent[0]["kind"] == "correction"


def test_add_ignores_blank_text(tmp_path):
    history = HistoryManager(file_path=tmp_path / "history.json")
    history.add("   ")
    assert history.get_recent() == []


def test_add_updates_timestamp_on_consecutive_duplicate(tmp_path):
    history = HistoryManager(file_path=tmp_path / "history.json")
    history.add("same text", kind="dictation")
    first_ts = history.get_recent(1)[0]["timestamp"]

    history.add("same text", kind="dictation")

    assert len(history.get_recent(10)) == 1
    assert history.get_recent(1)[0]["timestamp"] >= first_ts


def test_max_items_is_enforced(tmp_path):
    history = HistoryManager(file_path=tmp_path / "history.json", max_items=3)
    for i in range(5):
        history.add(f"item {i}")

    recent = history.get_recent(10)
    assert len(recent) == 3
    assert [item["text"] for item in recent] == ["item 4", "item 3", "item 2"]


def test_persists_to_disk_and_reloads(tmp_path):
    path = tmp_path / "history.json"
    history = HistoryManager(file_path=path)
    history.add("persisted text")

    reloaded = HistoryManager(file_path=path)
    assert [item["text"] for item in reloaded.get_recent()] == ["persisted text"]


def test_clear_empties_history_and_file(tmp_path):
    path = tmp_path / "history.json"
    history = HistoryManager(file_path=path)
    history.add("to be cleared")

    history.clear()

    assert history.get_recent() == []
    assert json.loads(path.read_text()) == []


def test_load_ignores_corrupt_file(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("not valid json")

    history = HistoryManager(file_path=path)

    assert history.get_recent() == []
