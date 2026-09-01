"""Shared Gemini API client setup for the transcriber and corrector.

Both callers need the same API-key resolution, `genai.Client` construction,
warning suppression, and token-usage debug logging; this base class keeps
that in one place instead of duplicated across both modules.
"""

import logging
import os
import warnings

try:
    from google import genai
except ImportError:
    genai = None

from .logger import get_logger

logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")


class GeminiClientBase:
    """Resolves the API key and builds the shared `genai.Client`."""

    def __init__(self, api_key: str | None, model: str, logger_name: str):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API Key not found! Please set GEMINI_API_KEY in ~/.config/dictation/.env or export it."
            )
        self.model = model
        self.client = genai.Client(api_key=self.api_key)
        self._logger = get_logger(logger_name)

    def _log_token_usage(self, usage) -> None:
        """Log prompt/thoughts/output token counts from a Gemini response, if present."""
        if not usage:
            return
        self._logger.debug(
            "Gemini tokens: prompt=%s thoughts=%s output=%s",
            usage.prompt_token_count,
            getattr(usage, "thoughts_token_count", 0),
            usage.candidates_token_count,
        )
