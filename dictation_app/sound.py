"""macOS system sound effects."""

import os
import subprocess

from .config import ENABLE_SOUNDS


def play_sound(sound_name: str):
    """Play macOS system sound asynchronously."""
    if not ENABLE_SOUNDS:
        return
    sound_path = f"/System/Library/Sounds/{sound_name}.aiff"
    if os.path.exists(sound_path):
        subprocess.Popen(["afplay", sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
