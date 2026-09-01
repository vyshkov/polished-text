"""Gemini Dictation & Text Corrector Engine for macOS.

Package layout:
- config.py:      environment-driven settings and shared constants
- sound.py:       macOS system sound effects
- clipboard.py:   clipboard, text selection, and paste helpers
- audio.py:       microphone recording and silence/noise detection
- transcriber.py: Gemini speech-to-text API calls
- corrector.py:   Gemini text correction & polishing API calls
- hud.py:         floating macOS HUD UI
- engine.py:      orchestrates recording, transcription, correction, hotkeys
- cli.py:         argument parsing and entrypoint
- caret.py:       Accessibility text caret / window bounds lookup
- notifications.py: macOS notification banners
"""
