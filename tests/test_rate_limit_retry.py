"""End-to-end tests for rate limit retry flow in DictationEngine."""

from unittest.mock import MagicMock, patch

from google.genai import errors as genai_errors

from dictation_app.engine import DictationEngine


def _api_error(code: int, message: str = "Rate limit") -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": message}})


@patch("dictation_app.engine.has_speech", return_value=True)
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.play_sound")
@patch("dictation_app.engine.save_model_to_env")
@patch("dictation_app.engine.prompt_model_switch_on_rate_limit")
def test_process_and_transcribe_retries_on_rate_limit_with_same_recording(
    mock_prompt,
    mock_save_env,
    mock_play_sound,
    mock_paste,
    mock_has_speech,
    tmp_path,
):
    fake_audio = tmp_path / "recording.flac"
    fake_audio.write_bytes(b"fake_audio_bytes")

    mock_prompt.return_value = "gemini-3.5-flash-lite"

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()
        engine.recorder = MagicMock()
        engine.recorder.stop.return_value = fake_audio

        mock_transcriber_1 = MagicMock()
        mock_transcriber_1.transcribe.side_effect = _api_error(429, "Resource exhausted")

        mock_transcriber_2 = MagicMock()
        mock_transcriber_2.transcribe.return_value = "Hello world from retry"

        with patch(
            "dictation_app.engine.GeminiTranscriber",
            side_effect=[mock_transcriber_1, mock_transcriber_2],
        ):
            engine.process_and_transcribe()

        mock_prompt.assert_called_once_with(
            current_model="gemini-3.6-flash",
            tried_models={"gemini-3.6-flash"},
        )
        assert engine.model == "gemini-3.5-flash-lite"

        # Verify the same fake_audio path was passed to retry
        mock_transcriber_1.transcribe.assert_called_once_with(fake_audio)
        mock_transcriber_2.transcribe.assert_called_once_with(fake_audio)

        # Verify text was pasted and success sound was played
        mock_paste.assert_called_once_with("Hello world from retry")
        mock_play_sound.assert_called_with("Hero")
        mock_save_env.assert_called_with("gemini-3.5-flash-lite")


@patch("dictation_app.engine.has_speech", return_value=True)
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.play_sound")
@patch("dictation_app.engine.save_model_to_env")
@patch("dictation_app.engine.prompt_model_switch_on_rate_limit")
def test_process_and_transcribe_cancelled_by_user_on_rate_limit(
    mock_prompt,
    mock_save_env,
    mock_play_sound,
    mock_paste,
    mock_has_speech,
    tmp_path,
):
    fake_audio = tmp_path / "recording.flac"
    fake_audio.write_bytes(b"fake_audio_bytes")

    mock_prompt.return_value = None  # User clicked Cancel

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()
        engine.recorder = MagicMock()
        engine.recorder.stop.return_value = fake_audio

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.side_effect = _api_error(429, "Quota exceeded")

        with patch("dictation_app.engine.GeminiTranscriber", return_value=mock_transcriber):
            engine.process_and_transcribe()

        mock_prompt.assert_called_once()
        assert engine.model == "gemini-3.6-flash"  # Not changed

        mock_paste.assert_not_called()
        engine.hud.show_cancelled.assert_called_with("⚠️  Rate limit")
        mock_play_sound.assert_called_with("Basso")


@patch("dictation_app.engine.has_speech", return_value=True)
@patch("dictation_app.engine.paste_text")
@patch("dictation_app.engine.play_sound")
@patch("dictation_app.engine.prompt_model_switch_on_rate_limit")
def test_process_and_transcribe_multiple_rate_limits_chain(
    mock_prompt,
    mock_play_sound,
    mock_paste,
    mock_has_speech,
    tmp_path,
):
    fake_audio = tmp_path / "recording.flac"
    fake_audio.write_bytes(b"fake_audio_bytes")

    # 1st rate limit switches to model B; 2nd rate limit switches to model C
    mock_prompt.side_effect = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()
        engine.recorder = MagicMock()
        engine.recorder.stop.return_value = fake_audio

        mock_t1 = MagicMock()
        mock_t1.transcribe.side_effect = _api_error(429, "Flash quota exhausted")

        mock_t2 = MagicMock()
        mock_t2.transcribe.side_effect = _api_error(429, "Flash-lite quota exhausted")

        mock_t3 = MagicMock()
        mock_t3.transcribe.return_value = "Success on third model"

        with (
            patch(
                "dictation_app.engine.GeminiTranscriber",
                side_effect=[mock_t1, mock_t2, mock_t3],
            ),
            patch("dictation_app.engine.save_model_to_env"),
        ):
            engine.process_and_transcribe()

        assert mock_prompt.call_count == 2
        assert engine.model == "gemini-3.5-flash"
        mock_t1.transcribe.assert_called_once_with(fake_audio)
        mock_t2.transcribe.assert_called_once_with(fake_audio)
        mock_t3.transcribe.assert_called_once_with(fake_audio)
        mock_paste.assert_called_once_with("Success on third model")


@patch("dictation_app.engine.has_speech", return_value=True)
@patch("dictation_app.engine.notify")
@patch("dictation_app.engine.prompt_model_switch_on_rate_limit")
def test_process_and_transcribe_non_rate_limit_error_does_not_prompt_switch(
    mock_prompt,
    mock_notify,
    mock_has_speech,
    tmp_path,
):
    fake_audio = tmp_path / "recording.flac"
    fake_audio.write_bytes(b"fake_audio_bytes")

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(model="gemini-3.6-flash")
        engine.hud = MagicMock()
        engine.recorder = MagicMock()
        engine.recorder.stop.return_value = fake_audio

        mock_t = MagicMock()
        mock_t.transcribe.side_effect = _api_error(401, "API key invalid")

        with patch("dictation_app.engine.GeminiTranscriber", return_value=mock_t):
            engine.process_and_transcribe()

        mock_prompt.assert_not_called()
        mock_notify.assert_called_once()
        assert "API key rejected" in mock_notify.call_args[0][1]
