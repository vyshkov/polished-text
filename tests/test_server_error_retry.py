"""End-to-end tests for 503 server error retry flow in DictationEngine."""

from unittest.mock import MagicMock, call, patch

from google.genai import errors as genai_errors

from dictation_app.config import AVAILABLE_CORRECTOR_MODELS, AVAILABLE_MODELS
from dictation_app.engine import DictationEngine


def _503_error(
    message: str = "The model is overloaded. Please try again later.",
) -> genai_errors.APIError:
    return genai_errors.APIError(503, {"error": {"message": message}})


@patch("dictation_app.engine.has_speech", return_value=True)
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.play_sound")
@patch("dictation_app.engine.save_model_to_env")
@patch("dictation_app.engine.prompt_server_error_retry")
def test_process_and_transcribe_retries_on_503_with_same_model(
    mock_prompt,
    mock_save_env,
    mock_play_sound,
    mock_paste,
    mock_has_speech,
    tmp_path,
):
    fake_audio = tmp_path / "recording.flac"
    fake_audio.write_bytes(b"fake_audio_bytes")

    # User clicks Retry with same model
    mock_prompt.return_value = "gemini-3.6-flash"

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()
        engine.recorder = MagicMock()
        engine.recorder.stop.return_value = fake_audio

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.side_effect = [_503_error(), "Success on retry"]

        with patch(
            "dictation_app.engine.GeminiTranscriber",
            return_value=mock_transcriber,
        ):
            engine.process_and_transcribe()

        mock_prompt.assert_called_once_with(
            current_model="gemini-3.6-flash",
            error_message="Gemini API error (503): The model is overloaded. Please try again later.",
            tried_models={"gemini-3.6-flash"},
            available_models=AVAILABLE_MODELS,
        )
        assert engine.model == "gemini-3.6-flash"

        # Verify same recording audio was passed to both attempts
        assert mock_transcriber.transcribe.call_count == 2
        mock_transcriber.transcribe.assert_has_calls([call(fake_audio), call(fake_audio)])

        mock_paste.assert_called_once_with("Success on retry")
        mock_play_sound.assert_called_with("Hero")


@patch("dictation_app.engine.has_speech", return_value=True)
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.play_sound")
@patch("dictation_app.engine.save_model_to_env")
@patch("dictation_app.engine.prompt_server_error_retry")
def test_process_and_transcribe_retries_on_503_with_switched_model(
    mock_prompt,
    mock_save_env,
    mock_play_sound,
    mock_paste,
    mock_has_speech,
    tmp_path,
):
    fake_audio = tmp_path / "recording.flac"
    fake_audio.write_bytes(b"fake_audio_bytes")

    # User picks another model from dropdown and clicks Retry
    mock_prompt.return_value = "gemini-3.8-flash"

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()
        engine.recorder = MagicMock()
        engine.recorder.stop.return_value = fake_audio

        mock_transcriber_1 = MagicMock()
        mock_transcriber_1.transcribe.side_effect = _503_error()

        mock_transcriber_2 = MagicMock()
        mock_transcriber_2.transcribe.return_value = "Hello from switched model"

        with patch(
            "dictation_app.engine.GeminiTranscriber",
            side_effect=[mock_transcriber_1, mock_transcriber_2],
        ):
            engine.process_and_transcribe()

        assert engine.model == "gemini-3.8-flash"
        mock_save_env.assert_called_with("gemini-3.8-flash")
        mock_paste.assert_called_once_with("Hello from switched model")
        mock_play_sound.assert_called_with("Hero")


@patch("dictation_app.engine.notify")
@patch("dictation_app.engine.has_speech", return_value=True)
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.play_sound")
@patch("dictation_app.engine.prompt_server_error_retry")
def test_process_and_transcribe_cancelled_on_503(
    mock_prompt,
    mock_play_sound,
    mock_paste,
    mock_has_speech,
    mock_notify,
    tmp_path,
):
    fake_audio = tmp_path / "recording.flac"
    fake_audio.write_bytes(b"fake_audio_bytes")

    # User clicks Cancel
    mock_prompt.return_value = None

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()
        engine.recorder = MagicMock()
        engine.recorder.stop.return_value = fake_audio

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.side_effect = _503_error()

        with patch("dictation_app.engine.GeminiTranscriber", return_value=mock_transcriber):
            engine.process_and_transcribe()

        mock_prompt.assert_called_once()
        assert engine.model == "gemini-3.6-flash"
        mock_paste.assert_not_called()
        engine.hud.show_cancelled.assert_called_with("⚠️  Cancelled")
        mock_play_sound.assert_called_with("Basso")
        # Ensure no intrusive error notification banner was shown
        mock_notify.assert_not_called()


@patch("dictation_app.engine.GeminiWriter")
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.get_clipboard_text")
@patch("dictation_app.engine.prompt_write_dialog")
@patch("dictation_app.engine.reactivate_app")
@patch("dictation_app.engine.get_frontmost_app")
@patch("dictation_app.engine.save_corrector_model_to_env")
@patch("dictation_app.engine.prompt_server_error_retry")
def test_prompt_and_write_retries_on_503_switch_model(
    mock_prompt_retry,
    mock_save_corr_env,
    mock_get_app,
    mock_reactivate,
    mock_write_dialog,
    mock_get_clip,
    mock_paste,
    mock_writer_cls,
):
    mock_get_app.return_value = MagicMock()
    mock_get_clip.return_value = ""
    mock_write_dialog.return_value = ("Draft summary", False)
    mock_prompt_retry.return_value = "gemini-3.8-flash"

    mock_writer_1 = MagicMock()
    mock_writer_1.model = "gemini-3.5-flash-lite"
    mock_writer_1.write.side_effect = _503_error()

    mock_writer_2 = MagicMock()
    mock_writer_2.model = "gemini-3.8-flash"
    mock_writer_2.write.return_value = "Summary written successfully."

    mock_writer_cls.side_effect = [mock_writer_1, mock_writer_2]

    engine = DictationEngine(corrector_model="gemini-3.5-flash-lite")
    engine.hud = MagicMock()
    engine.history = MagicMock()
    engine.menubar = MagicMock()

    engine.prompt_and_write()

    mock_prompt_retry.assert_called_once_with(
        current_model="gemini-3.5-flash-lite",
        error_message="Gemini API error (503): The model is overloaded. Please try again later.",
        tried_models={"gemini-3.5-flash-lite"},
        available_models=AVAILABLE_CORRECTOR_MODELS,
    )
    assert engine.corrector_model == "gemini-3.8-flash"
    mock_save_corr_env.assert_called_with("gemini-3.8-flash")
    mock_paste.assert_called_once_with("Summary written successfully.")


@patch("dictation_app.engine.notify")
@patch("dictation_app.engine.GeminiWriter")
@patch("dictation_app.engine.get_clipboard_text")
@patch("dictation_app.engine.prompt_write_dialog")
@patch("dictation_app.engine.prompt_server_error_retry")
def test_prompt_and_write_cancelled_on_503(
    mock_prompt_retry,
    mock_write_dialog,
    mock_get_clip,
    mock_writer_cls,
    mock_notify,
):
    mock_get_clip.return_value = ""
    mock_write_dialog.return_value = ("Draft summary", False)
    mock_prompt_retry.return_value = None  # user cancelled

    mock_writer = MagicMock()
    mock_writer.model = "gemini-3.5-flash-lite"
    mock_writer.write.side_effect = _503_error()
    mock_writer_cls.return_value = mock_writer

    engine = DictationEngine(corrector_model="gemini-3.5-flash-lite")
    engine.hud = MagicMock()

    engine.prompt_and_write()

    assert engine.corrector_model == "gemini-3.5-flash-lite"
    engine.hud.show_cancelled.assert_called_with("⚠️  Cancelled")
    mock_notify.assert_not_called()


@patch("dictation_app.engine.get_selected_text_info")
@patch("dictation_app.engine.GeminiCorrector")
@patch("dictation_app.engine.save_corrector_model_to_env")
@patch("dictation_app.engine.prompt_server_error_retry")
@patch("dictation_app.engine.replace_selected_text")
@patch("dictation_app.engine.play_sound")
def test_correct_selection_retries_on_503(
    mock_play_sound,
    mock_replace_selected,
    mock_prompt_retry,
    mock_save_corr_env,
    mock_corrector_cls,
    mock_selected_text_info,
):
    mock_selected_text_info.return_value = ("bad grammer", True, MagicMock())
    mock_prompt_retry.return_value = "gemini-3.8-flash"

    mock_corr_1 = MagicMock()
    mock_corr_1.model = "gemini-3.5-flash-lite"
    mock_corr_1.correct.side_effect = _503_error()

    mock_corr_2 = MagicMock()
    mock_corr_2.model = "gemini-3.8-flash"
    mock_corr_2.correct.return_value = "good grammar"

    mock_corrector_cls.side_effect = [mock_corr_1, mock_corr_2]

    engine = DictationEngine(corrector_model="gemini-3.5-flash-lite")
    engine.hud = MagicMock()
    engine.history = MagicMock()
    engine.menubar = MagicMock()

    engine.correct_selection()

    assert engine.corrector_model == "gemini-3.8-flash"
    mock_replace_selected.assert_called_once_with(
        "good grammar", mock_selected_text_info.return_value[2]
    )
    mock_play_sound.assert_called_with("Hero")
