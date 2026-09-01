"""Tests for GeminiTranscriber's describe_error API-error-to-message mapping."""

from google.genai import errors as genai_errors

from dictation_app.transcriber import describe_error


def _api_error(code: int, message: str = "boom") -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": message}})


def test_rate_limit_error_message():
    assert "Rate limit" in describe_error(_api_error(429))


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
