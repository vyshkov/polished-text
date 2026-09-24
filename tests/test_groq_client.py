"""Unit tests for Groq speech-to-text, corrector, and writer clients."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from dictation_app.corrector import GeminiCorrector, get_corrector
from dictation_app.groq_client import (
    GroqAccessDeniedError,
    GroqAuthError,
    GroqCorrector,
    GroqRateLimitError,
    GroqServerError,
    GroqTranscriber,
    GroqWriter,
    _handle_groq_error,
    _normalize_groq_model,
)
from dictation_app.transcriber import (
    describe_error,
    get_transcriber,
    is_rate_limit_error,
    is_server_error,
)
from dictation_app.writer import GeminiWriter, get_writer


def test_normalize_groq_model():
    assert _normalize_groq_model("groq:whisper-large-v3-turbo") == "whisper-large-v3-turbo"
    assert _normalize_groq_model("groq:openai/gpt-oss-120b") == "openai/gpt-oss-120b"
    assert _normalize_groq_model("whisper-large-v3") == "whisper-large-v3"
    assert _normalize_groq_model("") == ""


def test_error_handling_helpers():
    # 403 Cloudflare / Network settings block
    resp_403_net = httpx.Response(
        403,
        json={"error": {"message": "Access denied. Please check your network settings."}},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    with pytest.raises(GroqAccessDeniedError) as exc_403_net:
        _handle_groq_error(resp_403_net)
    assert "network" in str(exc_403_net.value).lower()
    assert "VPN/network" in describe_error(exc_403_net.value)

    # 401 Auth Error
    resp_401 = httpx.Response(
        401,
        json={"error": {"message": "Invalid API key", "type": "invalid_request_error"}},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    with pytest.raises(GroqAuthError) as exc_401:
        _handle_groq_error(resp_401)
    assert "rejected" in str(exc_401.value).lower()
    assert exc_401.value.status_code == 401

    # 429 Rate Limit
    resp_429 = httpx.Response(
        429,
        json={"error": {"message": "Rate limit reached", "code": "rate_limit_exceeded"}},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    with pytest.raises(GroqRateLimitError) as exc_429:
        _handle_groq_error(resp_429)
    assert "rate limit" in str(exc_429.value).lower()
    assert is_rate_limit_error(exc_429.value) is True
    assert is_server_error(exc_429.value) is False
    assert "rate limit" in describe_error(exc_429.value).lower()

    # 503 Server Error
    resp_503 = httpx.Response(
        503,
        json={"error": {"message": "Service unavailable"}},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    with pytest.raises(GroqServerError) as exc_503:
        _handle_groq_error(resp_503)
    assert is_server_error(exc_503.value) is True
    assert is_rate_limit_error(exc_503.value) is False
    assert "server error" in describe_error(exc_503.value).lower()


def test_groq_client_missing_api_key():
    transcriber = GroqTranscriber(api_key="", model="groq:whisper-large-v3-turbo")
    with patch("dictation_app.groq_client.GROQ_API_KEY", ""):
        transcriber.api_key = ""
        with pytest.raises(GroqAuthError) as exc:
            transcriber._headers()
        assert "not configured" in str(exc.value)


@patch.object(httpx.Client, "post")
def test_groq_transcriber_success(mock_post, tmp_path):
    audio_file = tmp_path / "test.flac"
    audio_file.write_bytes(b"dummy audio content")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "Hello world from Groq Whisper"}
    mock_post.return_value = mock_resp

    transcriber = GroqTranscriber(api_key="gsk_test123", model="groq:whisper-large-v3-turbo")
    result = transcriber.transcribe(audio_file)

    assert result == "Hello world from Groq Whisper"
    assert transcriber.model == "groq:whisper-large-v3-turbo"
    assert transcriber.api_model == "whisper-large-v3-turbo"

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "https://api.groq.com/openai/v1/audio/transcriptions" in args[0]
    assert kwargs["headers"]["Authorization"] == "Bearer gsk_test123"
    assert kwargs["data"]["model"] == "whisper-large-v3-turbo"
    assert kwargs["data"]["response_format"] == "json"


def test_groq_transcriber_empty_or_missing_file(tmp_path):
    transcriber = GroqTranscriber(api_key="gsk_test123")
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")

    assert transcriber.transcribe(empty_file) == ""

    missing_file = tmp_path / "missing.wav"
    assert transcriber.transcribe(missing_file) == ""


@patch.object(httpx.Client, "post")
def test_groq_corrector_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "This is polished and corrected text."}}]
    }
    mock_post.return_value = mock_resp

    corrector = GroqCorrector(api_key="gsk_test123", model="groq:openai/gpt-oss-120b")
    result = corrector.correct("this is unpolished txt")

    assert result == "This is polished and corrected text."
    assert corrector.model == "groq:openai/gpt-oss-120b"
    assert corrector.api_model == "openai/gpt-oss-120b"

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "https://api.groq.com/openai/v1/chat/completions" in args[0]
    payload = kwargs["json"]
    assert payload["model"] == "openai/gpt-oss-120b"
    assert payload["temperature"] == 0.2
    assert len(payload["messages"]) == 2
    assert payload["messages"][1]["content"] == "this is unpolished txt"


def test_groq_corrector_empty_text():
    corrector = GroqCorrector(api_key="gsk_test123")
    assert corrector.correct("") == ""
    assert corrector.correct("   \n\t  ") == ""


@patch.object(httpx.Client, "post")
def test_groq_writer_without_context(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": [{"message": {"content": "Here is drafted copy."}}]}
    mock_post.return_value = mock_resp

    writer = GroqWriter(api_key="gsk_test123", model="groq:openai/gpt-oss-120b")
    result = writer.write("Write an introduction")

    assert result == "Here is drafted copy."
    payload = mock_post.call_args.kwargs["json"]
    assert payload["model"] == "openai/gpt-oss-120b"
    assert "Instructions:\nWrite an introduction" in payload["messages"][1]["content"]


@patch.object(httpx.Client, "post")
def test_groq_writer_with_context(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Summary based on context."}}]
    }
    mock_post.return_value = mock_resp

    writer = GroqWriter(api_key="gsk_test123", model="groq:openai/gpt-oss-120b")
    result = writer.write("Summarize", context="Important project notes.")

    assert result == "Summary based on context."
    payload = mock_post.call_args.kwargs["json"]
    user_msg = payload["messages"][1]["content"]
    assert "Context / Reference Material:" in user_msg
    assert "Important project notes." in user_msg
    assert "Instructions:\nSummarize" in user_msg


def test_groq_writer_empty_prompt():
    writer = GroqWriter(api_key="gsk_test123")
    assert writer.write("") == ""
    assert writer.write("   ") == ""


def test_factory_functions():
    # Transcriber factory
    t_groq = get_transcriber("groq:whisper-large-v3-turbo")
    assert isinstance(t_groq, GroqTranscriber)
    assert t_groq.model == "groq:whisper-large-v3-turbo"

    # Corrector factory
    c_groq = get_corrector("groq:openai/gpt-oss-120b")
    assert isinstance(c_groq, GroqCorrector)
    assert c_groq.model == "groq:openai/gpt-oss-120b"

    with patch("dictation_app.gemini_client.genai.Client"):
        c_gemini = get_corrector("gemini-2.5-flash")
        assert isinstance(c_gemini, GeminiCorrector)

    # Writer factory
    w_groq = get_writer("groq:openai/gpt-oss-120b")
    assert isinstance(w_groq, GroqWriter)
    assert w_groq.model == "groq:openai/gpt-oss-120b"

    with patch("dictation_app.gemini_client.genai.Client"):
        w_gemini = get_writer("gemini-2.5-flash")
        assert isinstance(w_gemini, GeminiWriter)


def test_engine_groq_routing():
    from dictation_app.engine import DictationEngine

    with patch("dictation_app.engine.DictationMenuBar"):
        engine = DictationEngine(
            model="groq:whisper-large-v3-turbo",
            corrector_model="groq:openai/gpt-oss-120b",
        )
        engine.hud = MagicMock()

        # Check transcriber creation
        transcriber = engine._create_transcriber("groq:whisper-large-v3-turbo")
        assert isinstance(transcriber, GroqTranscriber)
        assert transcriber.model == "groq:whisper-large-v3-turbo"

        # Check corrector creation
        corrector = engine._create_corrector("groq:openai/gpt-oss-120b")
        assert isinstance(corrector, GroqCorrector)
        assert corrector.model == "groq:openai/gpt-oss-120b"

        # Check writer creation
        writer = engine._create_writer("groq:openai/gpt-oss-120b")
        assert isinstance(writer, GroqWriter)
        assert writer.model == "groq:openai/gpt-oss-120b"

        # Check engine properties
        assert isinstance(engine.transcriber, GroqTranscriber)
        assert isinstance(engine.corrector, GroqCorrector)
        assert isinstance(engine.writer, GroqWriter)


@patch("dictation_app.engine.save_model_to_env")
def test_engine_set_model_groq(mock_save_env):
    from dictation_app.engine import DictationEngine

    with (
        patch("dictation_app.engine.DictationMenuBar"),
        patch("dictation_app.gemini_client.genai.Client"),
    ):
        engine = DictationEngine(model="gemini-3.5-flash-lite")
        engine.hud = MagicMock()

        engine.set_model("groq:whisper-large-v3-turbo")

        assert engine.model == "groq:whisper-large-v3-turbo"
        mock_save_env.assert_called_once_with("groq:whisper-large-v3-turbo")
        assert isinstance(engine.transcriber, GroqTranscriber)
        engine.hud.show_done.assert_called_once()


@patch("dictation_app.engine.save_corrector_model_to_env")
def test_engine_set_corrector_model_groq(mock_save_env):
    from dictation_app.engine import DictationEngine

    with (
        patch("dictation_app.engine.DictationMenuBar"),
        patch("dictation_app.gemini_client.genai.Client"),
    ):
        engine = DictationEngine(corrector_model="gemini-3.5-flash-lite")
        engine.hud = MagicMock()

        engine.set_corrector_model("groq:openai/gpt-oss-120b")

        assert engine.corrector_model == "groq:openai/gpt-oss-120b"
        mock_save_env.assert_called_once_with("groq:openai/gpt-oss-120b")
        assert isinstance(engine.corrector, GroqCorrector)
        assert isinstance(engine.writer, GroqWriter)
        engine.hud.show_done.assert_called_once()
