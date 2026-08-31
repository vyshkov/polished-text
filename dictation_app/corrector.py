"""Gemini API calls for text correction, proofreading, and natural phrasing."""

import os
import sys
import logging
import warnings

logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: 'google-genai' package is not installed.")
    print("Please install dependencies: pip install -r ~/.config/dictation/requirements.txt")
    sys.exit(1)

from .config import DEFAULT_CORRECTOR_MODEL
from .transcriber import describe_error


class GeminiCorrector:
    """Proofreads and polishes text using Google Gemini Flash-Lite."""

    def __init__(self, api_key: str = None, model: str = DEFAULT_CORRECTOR_MODEL):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API Key not found! Please set GEMINI_API_KEY in ~/.config/dictation/.env or export it."
            )
        self.model = model
        self.client = genai.Client(api_key=self.api_key)

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

        response = self.client.models.generate_content(
            model=self.model,
            contents=[text],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )

        usage = response.usage_metadata
        if usage and os.getenv("DICTATION_DEBUG"):
            print(
                f"   ↳ tokens: prompt={usage.prompt_token_count} "
                f"thoughts={getattr(usage, 'thoughts_token_count', 0)} "
                f"output={usage.candidates_token_count}"
            )

        corrected = response.text.strip() if response.text else ""
        return corrected
