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
            "You are an expert text editor, copywriter, and proofreader acting as a top-tier writing assistant.\n"
            "Your task is to thoroughly polish the provided text by eliminating all correctness and clarity/conciseness issues:\n\n"
            "1. Correctness (Spelling, Grammar & Punctuation):\n"
            "- Fix all typos, spelling mistakes, and incorrect word forms.\n"
            "- Fix all grammatical errors: subject-verb agreement, verb tenses, pronoun case, and modifiers.\n"
            "- Fix punctuation (commas, apostrophes, semicolons, colons, hyphens) and capitalization (sentence beginnings, proper nouns, acronyms).\n"
            "- Correct commonly confused words (e.g., their/there/they're, its/it's, affect/effect, then/than).\n\n"
            "2. Clarity & Conciseness (Flow & Phrasing):\n"
            "- Eliminate wordiness, tautologies, and unnecessary filler words (e.g., 'in order to' -> 'to', 'due to the fact that' -> 'because').\n"
            "- Untangle convoluted or awkward sentence structures so the text reads smoothly, clearly, and effortlessly.\n"
            "- Fix run-on sentences and comma splices.\n"
            "- Replace clunky, unnatural phrasing with natural idioms and precise vocabulary.\n"
            "- Tighten weak passive voice into active voice when it improves clarity.\n\n"
            "3. Core Preservation Rules:\n"
            "- Strictly preserve the original meaning, intent, factual information, and author's tone.\n"
            "- Strictly preserve the original language (do NOT translate).\n"
            "- Preserve text structure: paragraphs, line breaks, bullet points, Markdown formatting, code, numbers, and URLs.\n"
            "- If the text has no errors or awkward phrasing, keep it unchanged.\n\n"
            "4. Output Format:\n"
            "- Output ONLY the final corrected text.\n"
            "- Never include surrounding quotes, markdown code fences (unless the input was code), introductory remarks, or explanations."
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


def get_corrector(model: str = DEFAULT_CORRECTOR_MODEL):
    """Return appropriate text corrector instance based on model name."""
    if model.startswith("groq"):
        from .groq_client import GroqCorrector

        return GroqCorrector(model=model)
    return GeminiCorrector(model=model)
