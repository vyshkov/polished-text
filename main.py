#!/usr/bin/env python3
"""
Gemini Dictation & Text Corrector Engine for macOS
--------------------------------------------------
Records audio from microphone on Right Command (⌘) key (or configurable hotkey),
transcribes it using Google Gemini API, and automatically pastes the transcription
into the currently active application.

Also proofreads & polishes selected text on screen via Right Command + Option (⌘ + ⌥).

Supports:
- Tap Right Command: Starts recording -> Tap again to stop and transcribe.
- Hold Right Command: Push-to-talk (records while holding, transcribes on release).
- Right Command + Option: Selected text corrector (fixes grammar, punctuation, and style).

This file is a thin entrypoint; the implementation lives in dictation_app/.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

# Automatically switch to the local virtualenv if running outside it
_script_dir = Path(__file__).resolve().parent
_venv_python = _script_dir / "venv" / "bin" / "python"
if _venv_python.exists() and sys.executable != str(_venv_python) and sys.prefix == sys.base_prefix:
    try:
        os.execv(str(_venv_python), [str(_venv_python), *sys.argv])
    except Exception:
        pass

RESTART_EXIT_CODE = 42

if __name__ == "__main__":
    # If this is the outer launcher process, supervise child execution and seamless restarts
    if os.environ.get("DICTATION_IS_CHILD") != "1":
        os.environ["DICTATION_IS_CHILD"] = "1"
        script_path = str(Path(__file__).resolve())
        while True:
            try:
                proc = subprocess.run([sys.executable, script_path, *sys.argv[1:]], check=False)
                if proc.returncode == RESTART_EXIT_CODE:
                    print("\n🔄 [Supervisor] Restarting Gemini Dictation...\n")
                    time.sleep(0.15)
                    continue
                sys.exit(proc.returncode)
            except KeyboardInterrupt:
                print("\n👋 Gemini Dictation stopped.")
                sys.exit(0)
    else:
        from dictation_app.cli import main

        main()
