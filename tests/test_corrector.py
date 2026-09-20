"""Tests for GeminiCorrector client."""

from unittest.mock import MagicMock, patch

from dictation_app.corrector import GeminiCorrector


@patch("dictation_app.gemini_client.genai.Client")
def test_corrector_basic(mock_genai_client):
    mock_instance = MagicMock()
    mock_genai_client.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.text = "This is the polished and corrected sentence."
    mock_response.usage_metadata = None
    mock_instance.models.generate_content.return_value = mock_response

    corrector = GeminiCorrector(api_key="test-key", model="gemini-3.5-flash-lite")
    input_text = "this are the unpolite and uncorrect sentance"
    result = corrector.correct(input_text)

    assert result == "This is the polished and corrected sentence."
    mock_instance.models.generate_content.assert_called_once()
    call_kwargs = mock_instance.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.5-flash-lite"
    assert call_kwargs["contents"] == [input_text]

    # Verify system instruction contains key Grammarly red & yellow directives
    config = call_kwargs["config"]
    instruction = config.system_instruction
    assert "1. Correctness (Spelling, Grammar & Punctuation):" in instruction
    assert "2. Clarity & Conciseness (Flow & Phrasing):" in instruction
    assert "3. Core Preservation Rules:" in instruction
    assert "4. Output Format:" in instruction
    assert config.temperature == 0.2


@patch("dictation_app.gemini_client.genai.Client")
def test_corrector_empty_text_returns_empty_string(mock_genai_client):
    corrector = GeminiCorrector(api_key="test-key")
    assert corrector.correct("") == ""
    assert corrector.correct("   \n\t  ") == ""
    mock_genai_client.return_value.models.generate_content.assert_not_called()


@patch("dictation_app.corrector.get_model_thinking_config")
@patch("dictation_app.gemini_client.genai.Client")
def test_corrector_with_thinking_config(mock_genai_client, mock_thinking_cfg):
    mock_thinking_cfg.return_value = {"thinking_budget": 100}
    mock_instance = MagicMock()
    mock_genai_client.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.text = "Corrected."
    mock_instance.models.generate_content.return_value = mock_response

    corrector = GeminiCorrector(api_key="test-key", model="gemini-3.6-flash")
    result = corrector.correct("Input text")

    assert result == "Corrected."
    call_kwargs = mock_instance.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].thinking_config.thinking_budget == 100
