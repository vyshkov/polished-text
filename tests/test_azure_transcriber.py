"""Tests for AzureTranscriber, language mapping, and error handling."""

from unittest.mock import MagicMock, patch

import pytest

from dictation_app.azure_client import (
    AzureSpeechAuthError,
    AzureSpeechError,
    AzureSpeechRateLimitError,
    AzureTranscriber,
)
from dictation_app.config import resolve_azure_language_tags


def test_resolve_azure_language_tags():
    # Standard language names from config
    tags = resolve_azure_language_tags(["English", "Ukrainian"])
    assert tags == ["en-US", "uk-UA"]

    # Lowercase names
    assert resolve_azure_language_tags(["spanish", "french"]) == ["es-ES", "fr-FR"]

    # Already BCP-47 tags
    assert resolve_azure_language_tags(["de-DE", "ja-JP"]) == ["de-DE", "ja-JP"]

    # Mixed & empty fallback
    assert resolve_azure_language_tags([]) == ["en-US"]


def test_azure_transcriber_missing_key():
    with pytest.raises(AzureSpeechAuthError) as exc_info:
        AzureTranscriber(api_key="", region="eastus", endpoint="")
    assert "API Key not found" in str(exc_info.value)
    assert exc_info.value.code == 401


def test_azure_transcriber_missing_region_and_endpoint():
    with pytest.raises(AzureSpeechAuthError) as exc_info:
        AzureTranscriber(api_key="valid-key", region="", endpoint="")
    assert "region or endpoint not found" in str(exc_info.value)
    assert exc_info.value.code == 401


def test_azure_transcriber_empty_or_nonexistent_audio(tmp_path):
    transcriber = AzureTranscriber(api_key="key", region="eastus")
    assert transcriber.transcribe(tmp_path / "nonexistent.flac") == ""

    empty_file = tmp_path / "empty.flac"
    empty_file.write_bytes(b"")
    assert transcriber.transcribe(empty_file) == ""


@patch("dictation_app.azure_client.subprocess.run")
def test_azure_transcriber_converts_flac_to_wav(mock_subproc, tmp_path):
    transcriber = AzureTranscriber(api_key="key", region="eastus")

    flac_file = tmp_path / "audio.flac"
    flac_file.write_bytes(b"fake_flac_data")

    with patch.object(transcriber, "_transcribe_wav", return_value="Test result") as mock_wav_tx:
        result = transcriber.transcribe(flac_file)

        assert result == "Test result"
        mock_subproc.assert_called_once()
        cmd = mock_subproc.call_args[0][0]
        assert cmd[0] == "sox"
        assert cmd[1] == str(flac_file)
        assert "-r" in cmd
        assert "16000" in cmd
        assert "-c" in cmd
        assert "1" in cmd
        mock_wav_tx.assert_called_once()


def test_azure_transcriber_wav_direct_no_conversion(tmp_path):
    transcriber = AzureTranscriber(api_key="key", region="eastus")

    wav_file = tmp_path / "audio.wav"
    wav_file.write_bytes(b"fake_wav_data")

    with (
        patch.object(transcriber, "_convert_to_wav") as mock_convert,
        patch.object(transcriber, "_transcribe_wav", return_value="Direct wav result"),
    ):
        result = transcriber.transcribe(wav_file)
        assert result == "Direct wav result"
        mock_convert.assert_not_called()


@patch("dictation_app.azure_client.speechsdk")
def test_transcribe_wav_success(mock_speechsdk, tmp_path):
    transcriber = AzureTranscriber(api_key="key", region="eastus", languages=["English"])
    fake_wav = tmp_path / "speech.wav"
    fake_wav.write_bytes(b"RIFF....")

    mock_recognizer = MagicMock()

    # Simulate recognized event callback
    def fake_start():
        on_rec_callback = mock_recognizer.recognized.connect.call_args[0][0]
        on_stop_callback = mock_recognizer.session_stopped.connect.call_args[0][0]

        mock_event = MagicMock()
        mock_event.result.reason = mock_speechsdk.ResultReason.RecognizedSpeech
        mock_event.result.text = "Transcribed text from Azure."
        on_rec_callback(mock_event)
        on_stop_callback(MagicMock())

    mock_recognizer.start_continuous_recognition.side_effect = fake_start
    mock_speechsdk.SpeechRecognizer.return_value = mock_recognizer

    result = transcriber._transcribe_wav(fake_wav, timeout=5.0)
    assert result == "Transcribed text from Azure."


@patch("dictation_app.azure_client.speechsdk")
def test_transcribe_wav_rate_limit_error(mock_speechsdk, tmp_path):
    transcriber = AzureTranscriber(api_key="key", region="eastus")
    fake_wav = tmp_path / "speech.wav"
    fake_wav.write_bytes(b"RIFF....")

    mock_recognizer = MagicMock()
    mock_speechsdk.CancellationReason.Error = 1
    mock_speechsdk.CancellationErrorCode.TooManyRequests = 7

    def fake_start():
        on_canceled_callback = mock_recognizer.canceled.connect.call_args[0][0]
        mock_event = MagicMock()
        mock_event.cancellation_details.reason = mock_speechsdk.CancellationReason.Error
        mock_event.cancellation_details.code = mock_speechsdk.CancellationErrorCode.TooManyRequests
        mock_event.cancellation_details.error_details = (
            "WebSocket upgrade failed: 429 Too Many Requests (Quota Exceeded)"
        )
        on_canceled_callback(mock_event)

    mock_recognizer.start_continuous_recognition.side_effect = fake_start
    mock_speechsdk.SpeechRecognizer.return_value = mock_recognizer

    with pytest.raises(AzureSpeechRateLimitError) as exc_info:
        transcriber._transcribe_wav(fake_wav, timeout=5.0)

    assert "rate limit / quota exceeded" in str(exc_info.value)
    assert exc_info.value.code == 429


@patch("dictation_app.azure_client.speechsdk")
def test_transcribe_wav_auth_error(mock_speechsdk, tmp_path):
    transcriber = AzureTranscriber(api_key="key", region="eastus")
    fake_wav = tmp_path / "speech.wav"
    fake_wav.write_bytes(b"RIFF....")

    mock_recognizer = MagicMock()
    mock_speechsdk.CancellationReason.Error = 1
    mock_speechsdk.CancellationErrorCode.AuthenticationFailure = 2

    def fake_start():
        on_canceled_callback = mock_recognizer.canceled.connect.call_args[0][0]
        mock_event = MagicMock()
        mock_event.cancellation_details.reason = mock_speechsdk.CancellationReason.Error
        mock_event.cancellation_details.code = (
            mock_speechsdk.CancellationErrorCode.AuthenticationFailure
        )
        mock_event.cancellation_details.error_details = (
            "Authentication error (401). Please check subscription information and region name."
        )
        on_canceled_callback(mock_event)

    mock_recognizer.start_continuous_recognition.side_effect = fake_start
    mock_speechsdk.SpeechRecognizer.return_value = mock_recognizer

    with pytest.raises(AzureSpeechAuthError) as exc_info:
        transcriber._transcribe_wav(fake_wav, timeout=5.0)

    assert "authentication failed" in str(exc_info.value)
    assert exc_info.value.code == 401


@patch("dictation_app.azure_client.speechsdk")
def test_transcribe_wav_generic_error(mock_speechsdk, tmp_path):
    transcriber = AzureTranscriber(api_key="key", region="eastus")
    fake_wav = tmp_path / "speech.wav"
    fake_wav.write_bytes(b"RIFF....")

    mock_recognizer = MagicMock()
    mock_speechsdk.CancellationReason.Error = 1
    mock_speechsdk.CancellationErrorCode.ConnectionFailure = 3

    def fake_start():
        on_canceled_callback = mock_recognizer.canceled.connect.call_args[0][0]
        mock_event = MagicMock()
        mock_event.cancellation_details.reason = mock_speechsdk.CancellationReason.Error
        mock_event.cancellation_details.code = (
            mock_speechsdk.CancellationErrorCode.ConnectionFailure
        )
        mock_event.cancellation_details.error_details = "Connection failed."
        on_canceled_callback(mock_event)

    mock_recognizer.start_continuous_recognition.side_effect = fake_start
    mock_speechsdk.SpeechRecognizer.return_value = mock_recognizer

    with pytest.raises(AzureSpeechError) as exc_info:
        transcriber._transcribe_wav(fake_wav, timeout=5.0)

    assert "Azure Speech error" in str(exc_info.value)
