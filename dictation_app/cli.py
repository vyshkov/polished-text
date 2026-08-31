"""Command-line entrypoint: argument parsing and engine startup."""

import argparse
import sys
import time

from .audio import get_audio_input_devices, get_default_input_device_name
from .config import DEFAULT_AUDIO_DEVICE, DEFAULT_CORRECTOR_MODEL, DEFAULT_HOTKEY, DEFAULT_MODEL
from .corrector import GeminiCorrector
from .engine import DictationEngine
from .logger import rotate_and_prune_logs


def main():
    rotate_and_prune_logs()
    parser = argparse.ArgumentParser(description="Gemini Speech-to-Text Dictation and Text Corrector Engine")
    parser.add_argument("--test", action="store_true", help="Run interactive single recording test in terminal")
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List all detected audio input devices (microphones) and exit",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=DEFAULT_AUDIO_DEVICE,
        help=f"Audio input device name (default: {DEFAULT_AUDIO_DEVICE})",
    )
    parser.add_argument(
        "--correct-test",
        type=str,
        nargs="?",
        const="i go yesterday to store and buyed some apple and orange it was very good weather outside",
        help="Test text correction on sample text",
    )
    parser.add_argument("--hotkey", type=str, default=DEFAULT_HOTKEY, help="Hotkey (default: cmd_r for Right Command)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help=f"Gemini model to use for dictation (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--corrector-model",
        type=str,
        default=DEFAULT_CORRECTOR_MODEL,
        help=f"Gemini model to use for text correction (default: {DEFAULT_CORRECTOR_MODEL})",
    )
    args = parser.parse_args()

    if args.list_devices:
        devices = get_audio_input_devices()
        default_name = get_default_input_device_name()
        print("=" * 65)
        print("  🎤 Detected Audio Input Devices (Microphones)")
        print("=" * 65)
        if not devices:
            print(f"  • {default_name} [System Default]")
        else:
            for dev in devices:
                marker = " [System Default]" if dev["is_default"] else ""
                print(f"  • {dev['name']}{marker}")
        print("=" * 65)
        print("  💡 To lock dictation to a specific microphone, set AUDIO_DEVICE")
        print("     in ~/.config/dictation/.env or pass --device '<name>'")
        print("=" * 65)
        sys.exit(0)

    if args.correct_test is not None:
        print(f"🤖 Testing Gemini text correction ({args.corrector_model})...")
        corrector = GeminiCorrector(model=args.corrector_model)
        print("📝 Original:")
        print(f"   {args.correct_test}")
        start_t = time.time()
        corrected = corrector.correct(args.correct_test)
        elapsed = time.time() - start_t
        print("✨ Corrected:")
        print(f"   {corrected}")
        print(f"⏱️  Completed in {elapsed:.2f}s")
        sys.exit(0)

    engine = DictationEngine(
        hotkey_str=args.hotkey,
        model=args.model,
        corrector_model=args.corrector_model,
        device_name=args.device,
    )

    if args.test:
        engine.run_once_interactive()
    else:
        try:
            engine.start_listener()
        except KeyboardInterrupt:
            print("\n👋 Engine stopped.")

