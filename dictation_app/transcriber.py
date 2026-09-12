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


def is_rate_limit_error(exc: Exception | None) -> bool:
    """Check if an exception represents a Gemini API rate limit or quota exhaustion (429)."""
    if exc is None:
        return False
    if genai_errors is not None and isinstance(exc, genai_errors.APIError) and exc.code == 429:
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, "429"):
        return True
    status = getattr(exc, "status", None)
    if str(status).upper() == "RESOURCE_EXHAUSTED":
        return True
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "429",
            "resource_exhausted",
            "rate limit",
            "quota exceeded",
            "free-tier quota",
            "quota_exceeded",
        )
    )


def describe_error(exc: Exception) -> str:
    """Turn a transcription exception into a short, user-facing reason."""
    if is_rate_limit_error(exc):
        return "Rate limit hit (free-tier quota exceeded) - wait a bit and try again."
    if genai_errors is not None and isinstance(exc, genai_errors.APIError):
        if exc.code in (401, 403):
            return "API key rejected - check GEMINI_API_KEY in ~/.config/dictation/.env."
        if isinstance(exc, genai_errors.ServerError):
            return f"Gemini server error ({exc.code}) - try again shortly."
        return f"Gemini API error ({exc.code}): {exc.message}"
    return str(exc)


def get_model_thinking_config(model: str):
    """Return appropriate ThinkingConfig for the Gemini model.

    - Audio-specialized models (e.g. gemini-3.5-transcribe) do not support thinking configs.
    - gemini-3.7, gemini-3.8, and gemini-flash-latest support thinking_budget=0 (disabling thinking).
    - Other Gemini 3.x models support thinking_level='minimal'.
    """
    if types is None:
        return None
    if "transcribe" in model:
        return None
    if "3.7" in model or "3.8" in model or model == "gemini-flash-latest":
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level="minimal")


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

        config_kwargs = {
            "system_instruction": system_instruction,
            "temperature": 0.0,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        thinking_cfg = get_model_thinking_config(self.model)
        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/flac",
                ),
                "Transcribe this speech verbatim.",
            ],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        self._log_token_usage(response.usage_metadata)

        text = response.text.strip() if response.text else ""
        return text
