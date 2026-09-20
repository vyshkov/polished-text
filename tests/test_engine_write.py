"""Tests for DictationEngine write text integration."""

from unittest.mock import MagicMock, patch

from dictation_app.engine import DictationEngine


@patch("dictation_app.engine.GeminiWriter")
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.get_clipboard_text")
@patch("dictation_app.engine.prompt_write_dialog")
@patch("dictation_app.engine.reactivate_app")
@patch("dictation_app.engine.get_frontmost_app")
def test_engine_prompt_and_write_success(
    mock_get_app,
    mock_reactivate,
    mock_dialog,
    mock_get_clip,
    mock_paste,
    mock_writer_cls,
):
    mock_app = MagicMock()
    mock_get_app.return_value = mock_app
    mock_get_clip.return_value = "Important context"
    mock_dialog.return_value = ("Write an email", True)

    mock_writer_instance = MagicMock()
    mock_writer_instance.model = "gemini-3.5-flash-lite"
    mock_writer_instance.write.return_value = "Dear Team, Here is the update."
    mock_writer_cls.return_value = mock_writer_instance

    engine = DictationEngine(hotkey_str="cmd_r", corrector_model="gemini-3.5-flash-lite")
    engine.hud = MagicMock()
    engine.history = MagicMock()
    engine.menubar = MagicMock()

    engine.prompt_and_write()

    mock_dialog.assert_called_once_with(
        clipboard_preview="Important context", model="gemini-3.5-flash-lite"
    )
    mock_writer_instance.write.assert_called_once_with(
        "Write an email", context="Important context"
    )
    mock_reactivate.assert_called_once_with(mock_app)
    engine.history.add.assert_called_once_with("Dear Team, Here is the update.", kind="write")
    mock_paste.assert_called_once_with("Dear Team, Here is the update.")
    engine.hud.show_done.assert_called_once_with("✍️  Written")


@patch("dictation_app.engine.GeminiWriter")
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.get_clipboard_text")
@patch("dictation_app.engine.prompt_write_dialog")
def test_engine_prompt_and_write_cancelled(mock_dialog, mock_get_clip, mock_paste, mock_writer_cls):
    mock_dialog.return_value = None

    mock_writer_instance = MagicMock()
    mock_writer_cls.return_value = mock_writer_instance

    engine = DictationEngine(hotkey_str="cmd_r")
    engine.hud = MagicMock()

    engine.prompt_and_write()

    mock_writer_instance.write.assert_not_called()
    mock_paste.assert_not_called()


@patch("dictation_app.engine.GeminiWriter")
@patch("dictation_app.engine.prompt_model_switch_on_rate_limit")
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.get_clipboard_text")
@patch("dictation_app.engine.prompt_write_dialog")
@patch("dictation_app.engine.reactivate_app")
@patch("dictation_app.engine.get_frontmost_app")
def test_engine_prompt_and_write_rate_limit_retry(
    mock_get_app,
    mock_reactivate,
    mock_dialog,
    mock_get_clip,
    mock_paste,
    mock_prompt_switch,
    mock_writer_cls,
):
    mock_dialog.return_value = ("Write a poem", False)
    mock_prompt_switch.return_value = "gemini-3.6-flash"

    class RateLimitErr(Exception):
        pass

    RateLimitErr.__name__ = "ResourceExhausted"

    writer1 = MagicMock()
    writer1.model = "gemini-3.5-flash-lite"
    writer1.write.side_effect = RateLimitErr("429 Resource Exhausted")

    writer2 = MagicMock()
    writer2.model = "gemini-3.6-flash"
    writer2.write.return_value = "Roses are red, violets are blue."

    mock_writer_cls.side_effect = [writer1, writer2]

    engine = DictationEngine(hotkey_str="cmd_r", corrector_model="gemini-3.5-flash-lite")
    engine.hud = MagicMock()
    engine.history = MagicMock()
    engine.menubar = MagicMock()

    with patch("dictation_app.engine.is_rate_limit_error", return_value=True):
        engine.prompt_and_write()

    mock_prompt_switch.assert_called_once()
    assert engine.corrector_model == "gemini-3.6-flash"
    mock_paste.assert_called_once_with("Roses are red, violets are blue.")
