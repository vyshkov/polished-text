"""Azure Speech Service client and transcription engine."""

import subprocess
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path

try:
    import azure.cognitiveservices.speech as speechsdk
except ImportError:
    speechsdk = None

from .config import (
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_REGION,
    AZURE_SPEECH_URL,
    DICTATION_LANGUAGES,
    resolve_azure_language_tags,
)
from .logger import get_logger

logger = get_logger("AzureTranscriber")


class AzureSpeechError(Exception):
    """Base exception for Azure Speech Service errors."""

    def __init__(
        self,
        message: str,
        code: int | str | None = None,
        details: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details or message


class AzureSpeechAuthError(AzureSpeechError):
    """Raised when Azure Speech credentials or region are invalid (401/403)."""


class AzureSpeechRateLimitError(AzureSpeechError):
    """Raised when Azure Speech rate limit or monthly quota (429) is exceeded."""


class AzureTranscriber:
    """Speech-to-text transcriber using Microsoft Azure Speech Service."""

    def __init__(
        self,
        api_key: str | None = None,
        region: str | None = None,
        endpoint: str | None = None,
        model: str = "azure-speech",
        languages: Sequence[str] | None = None,
    ):
        if speechsdk is None:
            raise ImportError(
                "The 'azure-cognitiveservices-speech' package is required for Azure Speech transcription. "
                "Install it using: pip install azure-cognitiveservices-speech"
            )

        self.model = model
        resolved_key = api_key if api_key is not None else AZURE_SPEECH_KEY
        resolved_region = region if region is not None else AZURE_SPEECH_REGION
        resolved_endpoint = endpoint if endpoint is not None else AZURE_SPEECH_URL

        self.api_key = (resolved_key or "").strip()
        self.region = (resolved_region or "").strip()
        self.endpoint = (resolved_endpoint or "").strip()
        self.languages = list(languages) if languages is not None else DICTATION_LANGUAGES

        if not self.api_key:
            raise AzureSpeechAuthError(
                "Azure Speech API Key not found! Please set AZURE_SPEECH_KEY in ~/.config/dictation/.env.",
                code=401,
            )
        if not self.region and not self.endpoint:
            raise AzureSpeechAuthError(
                "Azure Speech region or endpoint not found! Please set AZURE_SPEECH_REGION (e.g. 'eastus') "
                "or AZURE_SPEECH_URL in ~/.config/dictation/.env.",
                code=401,
            )

    def _convert_to_wav(self, audio_path: Path) -> Path:
        """Convert input audio (e.g. FLAC) to temporary 16kHz mono WAV for Azure Speech SDK."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav_path = Path(tmp.name)

        try:
            cmd = [
                "sox",
                str(audio_path),
                "-r",
                "16000",
                "-c",
                "1",
                "-b",
                "16",
                str(tmp_wav_path),
            ]
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=10,
            )
            return tmp_wav_path
        except Exception as e:
            tmp_wav_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to convert audio file to WAV for Azure Speech: {e}") from e

    def transcribe(self, audio_path: Path, timeout: float = 60.0) -> str:
        """Transcribe audio file using Azure Speech Service."""
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            return ""

        # Ensure audio is in uncompressed WAV format expected by macOS Azure Speech C++ SDK
        needs_cleanup = False
        if audio_path.suffix.lower() != ".wav":
            wav_path = self._convert_to_wav(audio_path)
            needs_cleanup = True
        else:
            wav_path = audio_path

        try:
            return self._transcribe_wav(wav_path, timeout=timeout)
        finally:
            if needs_cleanup:
                wav_path.unlink(missing_ok=True)

    def _transcribe_wav(self, wav_path: Path, timeout: float = 60.0) -> str:
        if self.endpoint:
            speech_config = speechsdk.SpeechConfig(
                subscription=self.api_key,
                endpoint=self.endpoint,
            )
        else:
            speech_config = speechsdk.SpeechConfig(
                subscription=self.api_key,
                region=self.region,
            )

        speech_config.enable_dictation()

        audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))

        language_tags = resolve_azure_language_tags(self.languages)
        logger.debug("Azure Speech language tags: %s", language_tags)

        if len(language_tags) == 1:
            speech_config.speech_recognition_language = language_tags[0]
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
            )
        else:
            # Azure auto-detect supports up to 4 candidate languages
            candidate_langs = language_tags[:4]
            auto_lang_config = speechsdk.AutoDetectSourceLanguageConfig(languages=candidate_langs)
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                auto_detect_source_language_config=auto_lang_config,
                audio_config=audio_config,
            )

        recognized_texts: list[str] = []
        cancellation_info: dict[str, str | int] = {}
        done = threading.Event()

        def on_recognized(evt):
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
                recognized_texts.append(evt.result.text)

        def on_canceled(evt):
            details = evt.cancellation_details
            cancellation_info["reason"] = getattr(details, "reason", None)
            cancellation_info["code"] = getattr(details, "code", None)
            cancellation_info["error_details"] = getattr(details, "error_details", "") or ""
            done.set()

        def on_session_stopped(_evt):
            done.set()

        recognizer.recognized.connect(on_recognized)
        recognizer.canceled.connect(on_canceled)
        recognizer.session_stopped.connect(on_session_stopped)

        recognizer.start_continuous_recognition()
        finished = done.wait(timeout=timeout)
        try:
            recognizer.stop_continuous_recognition()
        except Exception as e:
            logger.debug("Notice on stopping continuous recognition: %s", e)

        if not finished:
            logger.warning("Azure Speech transcription timed out after %.1fs", timeout)

        # Inspect if any cancellation error occurred
        if cancellation_info.get("reason") == speechsdk.CancellationReason.Error:
            err_code = cancellation_info.get("code")
            details_str = str(cancellation_info.get("error_details", ""))
            details_lower = details_str.lower()

            logger.error(
                "Azure Speech cancellation error: code=%s, details=%s",
                err_code,
                details_str,
            )

            # Check for Rate Limit / Quota Exceeded (429)
            is_rate_limit = (
                err_code == speechsdk.CancellationErrorCode.TooManyRequests
                or "429" in details_str
                or "too many requests" in details_lower
                or "quota" in details_lower
                or "rate limit" in details_lower
                or "concurrency" in details_lower
            )
            if is_rate_limit:
                raise AzureSpeechRateLimitError(
                    f"Azure Speech rate limit / quota exceeded (429): {details_str}",
                    code=429,
                    details=details_str,
                )

            # Check for Authentication Failure (401/403)
            is_auth_error = (
                err_code
                in (
                    speechsdk.CancellationErrorCode.AuthenticationFailure,
                    speechsdk.CancellationErrorCode.Forbidden,
                )
                or "401" in details_str
                or "403" in details_str
                or "authentication error" in details_lower
                or "access denied" in details_lower
            )
            if is_auth_error:
                raise AzureSpeechAuthError(
                    f"Azure Speech authentication failed: {details_str}",
                    code=401,
                    details=details_str,
                )

            raise AzureSpeechError(
                f"Azure Speech error: {details_str}",
                code=err_code,
                details=details_str,
            )

        return " ".join(recognized_texts).strip()
