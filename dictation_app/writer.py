"""Gemini API calls for text generation and drafting based on prompt and optional context."""

try:
    from google.genai import types
except ImportError:
    types = None

from .config import DEFAULT_CORRECTOR_MODEL
from .gemini_client import GeminiClientBase
from .transcriber import get_model_thinking_config


class GeminiWriter(GeminiClientBase):
    """Generates paragraphs and text using the selected Gemini model."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_CORRECTOR_MODEL):
        super().__init__(api_key, model, "Writer")

    def write(self, prompt: str, context: str | None = None) -> str:
        """Draft or write text based on the user's prompt and optional clipboard context."""
        prompt = prompt.strip() if prompt else ""
        if not prompt:
            return ""

        system_instruction = (
            "You are an expert copywriter and helpful writing assistant. "
            "Your task is to write high-quality, clear, well-structured text or paragraphs "
            "based strictly on the user's instructions. "
            "If reference or context material from the clipboard is provided, use it faithfully as context "
            "to inform the content, tone, or subject matter of your writing. "
            "Output ONLY the final drafted text without any introductory pleasantries "
            "(such as 'Here is...', 'Certainly!'), conversational filler, explanations, or surrounding quotes, "
            "unless explicitly requested by the user. "
            "Preserve the language implied by the user's instructions or context."
        )

        content_parts = []
        if context and context.strip():
            content_parts.append(
                f'Context / Reference Material:\n"""\n{context.strip()}\n"""\n\nInstructions:\n{prompt}'
            )
        else:
            content_parts.append(f"Instructions:\n{prompt}")

        config_kwargs = {
            "system_instruction": system_instruction,
            "temperature": 0.7,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        thinking_cfg = get_model_thinking_config(self.model)
        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        response = self.client.models.generate_content(
            model=self.model,
            contents=content_parts,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        self._log_token_usage(response.usage_metadata)

        draft = response.text.strip() if response.text else ""
        return draft


def get_writer(model: str = DEFAULT_CORRECTOR_MODEL):
    """Return appropriate text writer instance based on model name."""
    if model.startswith("groq"):
        from .groq_client import GroqWriter

        return GroqWriter(model=model)
    return GeminiWriter(model=model)
