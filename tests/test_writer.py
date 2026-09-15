"""Tests for GeminiWriter client."""

from unittest.mock import MagicMock, patch

from dictation_app.writer import GeminiWriter


@patch("dictation_app.gemini_client.genai.Client")
def test_writer_basic_prompt(mock_genai_client):
    mock_instance = MagicMock()
    mock_genai_client.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.text = "Here is the drafted paragraph."
    mock_response.usage_metadata = None
    mock_instance.models.generate_content.return_value = mock_response

    writer = GeminiWriter(api_key="test-key", model="gemini-3.5-flash-lite")
    result = writer.write("Write an intro")

    assert result == "Here is the drafted paragraph."
    mock_instance.models.generate_content.assert_called_once()
    call_kwargs = mock_instance.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.5-flash-lite"
    assert "Instructions:\nWrite an intro" in call_kwargs["contents"][0]


@patch("dictation_app.gemini_client.genai.Client")
def test_writer_with_context(mock_genai_client):
    mock_instance = MagicMock()
    mock_genai_client.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.text = "Summary of reference notes."
    mock_response.usage_metadata = None
    mock_instance.models.generate_content.return_value = mock_response

    writer = GeminiWriter(api_key="test-key", model="gemini-3.5-flash-lite")
    result = writer.write("Summarize this", context="Meeting notes: 1. Launch soon. 2. Fix bugs.")

    assert result == "Summary of reference notes."
    call_kwargs = mock_instance.models.generate_content.call_args.kwargs
    content = call_kwargs["contents"][0]
    assert "Context / Reference Material:" in content
    assert "Meeting notes: 1. Launch soon." in content
    assert "Instructions:\nSummarize this" in content


@patch("dictation_app.gemini_client.genai.Client")
def test_writer_empty_prompt_returns_empty_string(mock_genai_client):
    writer = GeminiWriter(api_key="test-key")
    result = writer.write("   ")
    assert result == ""
    mock_genai_client.return_value.models.generate_content.assert_not_called()
