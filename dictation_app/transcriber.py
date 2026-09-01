"""Gemini API calls for speech-to-text transcription."""

from pathlib import Path

try:
    from google.genai import errors as genai_errors
    from google.genai import types
except ImportError:
    types = None
    genai_errors = None

from .config import DEFAULT_MODEL, DICTATION_LANGUAGES
from .gemini_client import GeminiClientBase


def describe_error(exc: Exception) -> str:
    """Turn a transcription exception into a short, user-facing reason."""
    if genai_errors is not None and isinstance(exc, genai_errors.APIError):
        if exc.code == 429:
            return "Rate limit hit (free-tier quota exceeded) - wait a bit and try again."
        if exc.code in (401, 403):
            return "API key rejected - check GEMINI_API_KEY in ~/.config/dictation/.env."
        if isinstance(exc, genai_errors.ServerError):
            return f"Gemini server error ({exc.code}) - try again shortly."
        return f"Gemini API error ({exc.code}): {exc.message}"
    return str(exc)


class GeminiTranscriber(GeminiClientBase):
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        super().__init__(api_key, model, "Transcriber")

    def transcribe(self, audio_path: Path) -> str:
        """Transcribe audio file using Google GenAI SDK."""
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            return ""

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        languages_hint = (
            f"The speaker only ever uses one of these languages: {', '.join(DICTATION_LANGUAGES)}. "
            "Detect which one is being spoken and transcribe in that language's native script "
            "(do not translate). "
            if DICTATION_LANGUAGES
            else ""
        )
        system_instruction = (
            "You are a fast, precise speech-to-text dictation engine. "
            f"{languages_hint}"
            "Transcribe the provided audio, but clean it up for written dictation: "
            'remove filler words and verbal disfluencies (e.g. "uh", "um", "er", "ah", '
            '"like", "you know") and drop false starts and stutter-repeated words. '
            "Do not otherwise rephrase, summarize, or correct grammar/word choice beyond that. "
            "Add correct punctuation and capitalization. "
            "Output ONLY the transcribed text without quotes, explanations, or introductory remarks."
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/flac",
                ),
                "Transcribe this speech verbatim.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,
                # thinking_budget is a token-count knob meant for older models; gemini-3.x
                # models are controlled via thinking_level, so set it directly to "minimal"
                # (and drop thinking_budget, which can otherwise be ignored/misread and leave
                # dynamic thinking on, adding avoidable latency).
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )

        self._log_token_usage(response.usage_metadata)

        text = response.text.strip() if response.text else ""
        return text
