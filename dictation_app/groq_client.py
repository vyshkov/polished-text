"""Groq API client and models for speech-to-text, text correction, and drafting."""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import httpx

from .config import DICTATION_LANGUAGES, GROQ_API_KEY, resolve_language_iso
from .logger import get_logger

logger = get_logger("GroqClient")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqError(Exception):
    """Base exception for Groq API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        code: str | None = None,
        details: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code or str(status_code)
        self.details = details or message


class GroqAuthError(GroqError):
    """Raised when Groq API key is invalid or unauthorized (401/403)."""


class GroqAccessDeniedError(GroqError):
    """Raised when Groq/Cloudflare blocks access due to network, VPN, datacenter IP, or geo-blocking (403)."""


class GroqRateLimitError(GroqError):
    """Raised when Groq rate limits or token quotas are exceeded (429)."""


class GroqServerError(GroqError):
    """Raised when Groq server returns 500/502/503/504."""


def _normalize_groq_model(model: str) -> str:
    """Strip 'groq:' prefix if present."""
    if model.startswith("groq:"):
        return model[5:]
    return model


def _handle_groq_error(response: httpx.Response) -> None:
    """Parse Groq error response and raise specific GroqError subclass."""
    status = response.status_code
    err_code = None
    err_msg = response.text

    try:
        data = response.json()
        if isinstance(data, dict) and "error" in data:
            err_dict = data["error"]
            err_msg = err_dict.get("message", response.text)
            err_code = err_dict.get("code")
    except Exception:
        pass

    if status == 403 and any(
        kw in err_msg.lower()
        for kw in ("network settings", "access denied", "blocked by cloudflare")
    ):
        raise GroqAccessDeniedError(
            f"Groq access blocked by network/VPN settings ({status}): {err_msg}",
            status_code=status,
            code=err_code or "access_denied",
            details=err_msg,
        )
    elif status in (401, 403):
        raise GroqAuthError(
            f"Groq API key rejected ({status}): {err_msg}",
            status_code=status,
            code=err_code,
            details=err_msg,
        )
    elif status == 429:
        raise GroqRateLimitError(
            f"Groq rate limit exceeded (429): {err_msg}",
            status_code=status,
            code=err_code or "429",
            details=err_msg,
        )
    elif status >= 500:
        raise GroqServerError(
            f"Groq server error ({status}): {err_msg}",
            status_code=status,
            code=err_code or str(status),
            details=err_msg,
        )
    else:
        raise GroqError(
            f"Groq request failed ({status}): {err_msg}",
            status_code=status,
            code=err_code or str(status),
            details=err_msg,
        )


class GroqClientBase:
    """Base client for Groq API requests with authentication and error handling."""

    def __init__(self, api_key: str | None = None, model: str = ""):
        self.api_key = (api_key or GROQ_API_KEY or "").strip()
        self.model = model
        self.api_model = _normalize_groq_model(model)
        self.client = httpx.Client(timeout=45.0)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise GroqAuthError(
                "Groq API key not configured. Please add GROQ_API_KEY in ~/.config/dictation/.env."
            )
        return {"Authorization": f"Bearer {self.api_key}"}


class GroqTranscriber(GroqClientBase):
    """Transcribes audio using Groq Whisper models (whisper-large-v3-turbo, whisper-large-v3)."""

    SLAVIC_OR_CYRILLIC_LANGUAGES: ClassVar[set[str]] = {
        "russian",
        "ru",
        "bulgarian",
        "bg",
        "belarusian",
        "be",
        "serbian",
        "sr",
        "polish",
        "pl",
        "macedonian",
        "mk",
        "slovak",
        "sk",
        "czech",
        "cs",
        "slovenian",
        "sl",
        "croatian",
        "hr",
    }
    RUSSIAN_ONLY_CHARS: ClassVar[set[str]] = set("ыэъёЫЭЪЁ")

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "groq:whisper-large-v3-turbo",
        languages: Sequence[str] | None = None,
    ):
        super().__init__(api_key=api_key, model=model)
        self.languages = list(languages) if languages is not None else list(DICTATION_LANGUAGES)

    def transcribe(self, audio_path: Path) -> str:
        """Transcribe an audio file using Groq /v1/audio/transcriptions endpoint.

        Automatically manages dual-language English/Ukrainian recognition:
        - If unconstrained Whisper detects a language outside allowed languages (e.g.
          misidentifying short Ukrainian speech as Russian/Bulgarian/etc.), it automatically
          re-transcribes with the correct target language in ~200ms without manual intervention.
        """
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            return ""

        url = f"{GROQ_BASE_URL}/audio/transcriptions"
        mime_type = "audio/flac" if audio_path.suffix.lower() == ".flac" else "audio/wav"

        # Determine allowed language codes and names
        configured_langs = [lang.strip() for lang in self.languages if lang.strip()]
        allowed_iso_codes = [resolve_language_iso(lang) for lang in configured_langs]

        # Case 1: If strictly single language is configured, lock it directly
        if len(allowed_iso_codes) == 1:
            data = {
                "model": self.api_model,
                "response_format": "json",
                "language": allowed_iso_codes[0],
            }
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path.name, f, mime_type)}
                try:
                    response = self.client.post(
                        url,
                        headers=self._headers(),
                        data=data,
                        files=files,
                    )
                except httpx.RequestError as exc:
                    raise GroqError(f"Network error communicating with Groq: {exc}") from exc

            if response.status_code != 200:
                _handle_groq_error(response)

            res_json = response.json()
            transcribed_text = str(res_json.get("text") or "").strip()
            logger.info(
                "Groq transcribed audio (single language %s) in model %s: %d chars",
                allowed_iso_codes[0],
                self.model,
                len(transcribed_text),
            )
            return transcribed_text

        # Case 2: Multilingual / bilingual (e.g. English and Ukrainian)
        # Pass 1: Auto-detection with verbose_json metadata
        data = {
            "model": self.api_model,
            "response_format": "verbose_json",
        }

        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, mime_type)}
            try:
                response = self.client.post(
                    url,
                    headers=self._headers(),
                    data=data,
                    files=files,
                )
            except httpx.RequestError as exc:
                raise GroqError(f"Network error communicating with Groq: {exc}") from exc

        if response.status_code != 200:
            _handle_groq_error(response)

        res_json = response.json()
        detected_lang = str(res_json.get("language") or "").strip().lower()
        transcribed_text = str(res_json.get("text") or "").strip()

        # Build allowed lookup sets for language matching
        allowed_set = set(allowed_iso_codes)
        for lang in configured_langs:
            allowed_set.add(lang.lower())

        has_cyrillic = any("\u0400" <= c <= "\u04ff" for c in transcribed_text)
        has_russian_chars = any(c in self.RUSSIAN_ONLY_CHARS for c in transcribed_text)

        # Verification rules:
        # 1. English: detected as english/en and text is Latin
        is_verified_english = (
            detected_lang in ("english", "en")
            and not has_cyrillic
            and ("en" in allowed_iso_codes or "english" in allowed_set)
        )
        # 2. Ukrainian: detected as ukrainian/uk and has no Russian-specific letters
        is_verified_ukrainian = (
            detected_lang in ("ukrainian", "uk")
            and not has_russian_chars
            and ("uk" in allowed_iso_codes or "ukrainian" in allowed_set)
        )

        if not detected_lang or is_verified_english or is_verified_ukrainian:
            logger.info(
                "Groq transcribed audio (%s) in model %s: %d chars",
                detected_lang or "auto",
                self.model,
                len(transcribed_text),
            )
            return transcribed_text

        # If detected language is not allowed or Russian letters leaked, determine correct fallback
        if detected_lang in self.SLAVIC_OR_CYRILLIC_LANGUAGES or has_cyrillic or has_russian_chars:
            fallback_lang = "uk" if "uk" in allowed_iso_codes else allowed_iso_codes[0]
        else:
            fallback_lang = "en" if "en" in allowed_iso_codes else allowed_iso_codes[0]

        logger.info(
            "Groq auto-detected '%s' (not in allowed %s); instantly re-transcribing with language='%s'",
            detected_lang,
            self.languages,
            fallback_lang,
        )

        retry_data = {
            "model": self.api_model,
            "response_format": "json",
            "language": fallback_lang,
        }

        with open(audio_path, "rb") as f2:
            files_retry = {"file": (audio_path.name, f2, mime_type)}
            try:
                response_retry = self.client.post(
                    url,
                    headers=self._headers(),
                    data=retry_data,
                    files=files_retry,
                )
            except httpx.RequestError as exc:
                raise GroqError(f"Network error communicating with Groq: {exc}") from exc

        if response_retry.status_code != 200:
            _handle_groq_error(response_retry)

        res2_json = response_retry.json()
        corrected_text = str(res2_json.get("text") or "").strip()
        logger.info(
            "Groq auto-corrected transcription (%s -> %s) in model %s: %d chars",
            detected_lang,
            fallback_lang,
            self.model,
            len(corrected_text),
        )
        return corrected_text


class GroqCorrector(GroqClientBase):
    """Proofreads and polishes text using Groq LLM chat completions."""

    def __init__(self, api_key: str | None = None, model: str = "groq:openai/gpt-oss-120b"):
        super().__init__(api_key=api_key, model=model)

    def correct(self, text: str) -> str:
        """Correct text for Grammarly red (correctness) & yellow (clarity) issues."""
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

        url = f"{GROQ_BASE_URL}/chat/completions"
        payload = {
            "model": self.api_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }

        headers = self._headers()
        headers["Content-Type"] = "application/json"

        try:
            response = self.client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise GroqError(f"Network error communicating with Groq: {exc}") from exc

        if response.status_code != 200:
            _handle_groq_error(response)

        res_json = response.json()
        choices = res_json.get("choices") or []
        if not choices:
            return ""

        corrected = str(choices[0].get("message", {}).get("content") or "").strip()
        logger.info("Groq corrected text with model %s (%d chars)", self.model, len(corrected))
        return corrected


class GroqWriter(GroqClientBase):
    """Drafts and generates text using Groq LLM chat completions based on instructions and context."""

    def __init__(self, api_key: str | None = None, model: str = "groq:openai/gpt-oss-120b"):
        super().__init__(api_key=api_key, model=model)

    def write(self, prompt: str, context: str | None = None) -> str:
        """Draft text based on prompt and optional context."""
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

        if context and context.strip():
            user_content = f'Context / Reference Material:\n"""\n{context.strip()}\n"""\n\nInstructions:\n{prompt}'
        else:
            user_content = f"Instructions:\n{prompt}"

        url = f"{GROQ_BASE_URL}/chat/completions"
        payload = {
            "model": self.api_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.7,
        }

        headers = self._headers()
        headers["Content-Type"] = "application/json"

        try:
            response = self.client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise GroqError(f"Network error communicating with Groq: {exc}") from exc

        if response.status_code != 200:
            _handle_groq_error(response)

        res_json = response.json()
        choices = res_json.get("choices") or []
        if not choices:
            return ""

        drafted = str(choices[0].get("message", {}).get("content") or "").strip()
        logger.info("Groq drafted text with model %s (%d chars)", self.model, len(drafted))
        return drafted
