"""Tests for dictation_app.dialogs helper functions and rate limit prompt."""

import json
from unittest.mock import MagicMock, patch

from dictation_app.dialogs import (
    _prompt_model_picker,
    _prompt_write_applescript,
    get_fallback_models,
    prompt_model_switch_on_rate_limit,
    prompt_write_dialog,
)

CUSTOM_MODELS = [
    ("model-a", "Model Alpha"),
    ("model-b", "Model Beta"),
    ("model-c", "Model Gamma"),
]


def test_get_fallback_models_excludes_current():
    fallbacks = get_fallback_models("model-a", available_models=CUSTOM_MODELS)
    assert len(fallbacks) == 2
    assert fallbacks[0] == ("model-b", "Model Beta")
    assert fallbacks[1] == ("model-c", "Model Gamma")


def test_get_fallback_models_excludes_tried():
    fallbacks = get_fallback_models(
        "model-a",
        tried_models={"model-b"},
        available_models=CUSTOM_MODELS,
    )
    assert len(fallbacks) == 1
    assert fallbacks[0] == ("model-c", "Model Gamma")


def test_get_fallback_models_exhausted():
    fallbacks = get_fallback_models(
        "model-a",
        tried_models={"model-b", "model-c"},
        available_models=CUSTOM_MODELS,
    )
    assert fallbacks == []


@patch("dictation_app.dialogs.subprocess.run")
@patch("dictation_app.dialogs.reactivate_app")
@patch("dictation_app.dialogs.get_frontmost_app")
def test_prompt_model_switch_accept_suggested(mock_get_app, mock_reactivate, mock_subproc):
    mock_app = MagicMock()
    mock_get_app.return_value = mock_app

    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout="Switch & Retry\n",
    )

    result = prompt_model_switch_on_rate_limit(
        "model-a",
        available_models=CUSTOM_MODELS,
    )

    assert result == "model-b"
    mock_reactivate.assert_called_once_with(mock_app)
    mock_subproc.assert_called_once()
    called_script = mock_subproc.call_args[0][0][2]
    assert "Model Alpha" in called_script
    assert "Model Beta" in called_script


@patch("dictation_app.dialogs.subprocess.run")
@patch("dictation_app.dialogs.reactivate_app")
@patch("dictation_app.dialogs.get_frontmost_app")
def test_prompt_model_switch_cancel(mock_get_app, mock_reactivate, mock_subproc):
    mock_get_app.return_value = MagicMock()
    mock_subproc.return_value = MagicMock(
        returncode=1,
        stdout="",
    )

    result = prompt_model_switch_on_rate_limit(
        "model-a",
        available_models=CUSTOM_MODELS,
    )

    assert result is None
    mock_reactivate.assert_not_called()


@patch("dictation_app.dialogs._prompt_model_picker")
@patch("dictation_app.dialogs.subprocess.run")
@patch("dictation_app.dialogs.reactivate_app")
@patch("dictation_app.dialogs.get_frontmost_app")
def test_prompt_model_switch_select_other_model(
    mock_get_app, mock_reactivate, mock_subproc, mock_picker
):
    mock_app = MagicMock()
    mock_get_app.return_value = mock_app
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout="Other Models...\n",
    )
    mock_picker.return_value = "model-c"

    result = prompt_model_switch_on_rate_limit(
        "model-a",
        available_models=CUSTOM_MODELS,
    )

    assert result == "model-c"
    mock_reactivate.assert_called_once_with(mock_app)
    mock_picker.assert_called_once()


@patch("dictation_app.dialogs._show_all_exhausted_dialog")
def test_prompt_model_switch_when_exhausted(mock_exhausted_dialog):
    result = prompt_model_switch_on_rate_limit(
        "model-a",
        tried_models={"model-b", "model-c"},
        available_models=CUSTOM_MODELS,
    )
    assert result is None
    mock_exhausted_dialog.assert_called_once()


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_model_picker_success(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout="Model Gamma\n",
    )

    candidates = [("model-b", "Model Beta"), ("model-c", "Model Gamma")]
    chosen = _prompt_model_picker(candidates, "Model Beta")

    assert chosen == "model-c"


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_model_picker_cancel(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout="CANCEL\n",
    )

    candidates = [("model-b", "Model Beta"), ("model-c", "Model Gamma")]
    chosen = _prompt_model_picker(candidates, "Model Beta")

    assert chosen is None


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_write_dialog_success_with_clipboard(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps(
            {"status": "ok", "prompt": "Write a thank you note", "include_clipboard": True}
        )
        + "\n",
    )

    result = prompt_write_dialog(clipboard_preview="Some notes from meeting")
    assert result == ("Write a thank you note", True)


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_write_dialog_success_without_clipboard(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps(
            {"status": "ok", "prompt": "Write a quick summary", "include_clipboard": False}
        )
        + "\n",
    )

    result = prompt_write_dialog(clipboard_preview="")
    assert result == ("Write a quick summary", False)


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_write_dialog_cancelled(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({"status": "cancelled"}) + "\n",
    )

    result = prompt_write_dialog()
    assert result is None


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_write_dialog_empty_prompt_returns_none(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({"status": "ok", "prompt": "   ", "include_clipboard": True}) + "\n",
    )

    result = prompt_write_dialog()
    assert result is None


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_write_applescript_success(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout="Write\nHello world\n",
    )

    result = _prompt_write_applescript()
    assert result == ("Hello world", False)


@patch("dictation_app.dialogs.subprocess.run")
def test_prompt_write_applescript_with_context(mock_subproc):
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout="Write + Context\nSummarize this\n",
    )

    result = _prompt_write_applescript(clipboard_preview="Some context")
    assert result == ("Summarize this", True)
