"""Gemini API calls for text correction, proofreading, and natural phrasing."""

try:
    from google.genai import types
except ImportError:
    types = None

from .config import DEFAULT_CORRECTOR_MODEL
from .gemini_client import GeminiClientBase
from .transcriber import get_model_thinking_config


class GeminiCorrector(GeminiClientBase):
    """Proofreads and polishes text using Google Gemini Flash-Lite."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_CORRECTOR_MODEL):
        super().__init__(api_key, model, "Corrector")

    def correct(self, text: str) -> str:
        """Correct punctuation, grammar, awkward phrasing, and style while preserving meaning."""
        text = text.strip() if text else ""
        if not text:
            return ""

        system_instruction = (
            "You are an expert text editor, copywriter, and proofreader. "
            "Correct the provided text: add proper punctuation and capitalization, fix grammatical "
            "and stylistic problems, remove awkward words and unnatural combinations, "
            "and make it sound natural, clear, and fluent while strictly preserving the original meaning "
            "and language (do not translate). "
            "Output ONLY the corrected text without any surrounding quotes, introductory remarks, "
            "markdown formatting, or explanations."
        )

        config_kwargs = {
            "system_instruction": system_instruction,
            "temperature": 0.2,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        thinking_cfg = get_model_thinking_config(self.model)
        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        response = self.client.models.generate_content(
            model=self.model,
            contents=[text],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        self._log_token_usage(response.usage_metadata)

        corrected = response.text.strip() if response.text else ""
        return corrected
