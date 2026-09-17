"""Tests for GeminiTranscriber's describe_error API-error-to-message mapping."""

from google.genai import errors as genai_errors

from dictation_app.transcriber import describe_error, is_rate_limit_error, is_server_error


def _api_error(code: int, message: str = "boom") -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": message}})


def test_rate_limit_error_message():
    assert "Rate limit" in describe_error(_api_error(429))


def test_is_rate_limit_error():
    assert is_rate_limit_error(_api_error(429)) is True
    assert is_rate_limit_error(_api_error(403)) is False
    assert is_rate_limit_error(None) is False
    assert is_rate_limit_error(Exception("RESOURCE_EXHAUSTED: quota exceeded")) is True
    assert is_rate_limit_error(Exception("429 Too Many Requests")) is True
    assert is_rate_limit_error(ValueError("Normal connection error")) is False


def test_is_server_error():
    assert is_server_error(_api_error(503)) is True
    assert is_server_error(_api_error(429)) is False
    assert is_server_error(_api_error(403)) is False
    assert is_server_error(None) is False
    assert (
        is_server_error(
            genai_errors.ServerError(503, {"error": {"message": "Service Unavailable"}})
        )
        is True
    )
    assert is_server_error(Exception("503 Service Unavailable")) is True
    assert is_server_error(Exception("The model is overloaded. Please try again later.")) is True
    assert is_server_error(ValueError("Normal connection error")) is False


def test_auth_error_message_for_401_and_403():
    assert "API key rejected" in describe_error(_api_error(401))
    assert "API key rejected" in describe_error(_api_error(403))


def test_server_error_message():
    err = genai_errors.ServerError(500, {"error": {"message": "boom"}})
    assert "Gemini server error (500)" in describe_error(err)


def test_generic_api_error_includes_code_and_message():
    err = _api_error(418, "I'm a teapot")
    described = describe_error(err)
    assert "418" in described
    assert "I'm a teapot" in described


def test_non_api_error_falls_back_to_str():
    assert describe_error(ValueError("network down")) == "network down"


def test_azure_rate_limit_error():
    from dictation_app.azure_client import AzureSpeechRateLimitError

    err = AzureSpeechRateLimitError("429 Too Many Requests (Quota Exceeded)", code=429)
    assert is_rate_limit_error(err) is True
    assert "Azure Speech rate limit hit" in describe_error(err)


def test_azure_auth_error_message():
    from dictation_app.azure_client import AzureSpeechAuthError

    err = AzureSpeechAuthError("Authentication error (401)", code=401)
    assert is_rate_limit_error(err) is False
    assert "AZURE_SPEECH_KEY" in describe_error(err)


def test_azure_generic_error_message():
    from dictation_app.azure_client import AzureSpeechError

    err = AzureSpeechError("Internal server error", code=500)
    assert "Azure Speech error: Internal server error" in describe_error(err)
