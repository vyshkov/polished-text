# 🎙️ Gemini Speech-to-Text Dictation & Text Corrector for macOS

A lightweight, high-performance dictation and text polishing tool powered by Google Gemini (Gemini 3.5 Flash / Flash-Lite), PyObjC, and SoX.

## 🪟 Floating Dynamic HUD
The engine includes a native macOS floating HUD pill indicator (Dynamic Island style):
- **🔴 Listening... / Equalizer**: Appears near the text caret when audio capture starts.
- **⚡ Transcribing... / Correcting...**: Shows progress while Gemini processes audio or text.
- **✨ Done**: Confirms completion before smoothly fading away.
- **Non-intrusive**: Never steals keyboard focus or interrupts typing.

---

## 📍 Menu Bar Icon & Recent History
A native macOS status item in the top panel (menu bar):
- **Recent History (Last 5)**: View your recent dictations (`🎙️`) and text corrections (`✍️`).
- **One-Click Copy**: Click any recent item to immediately copy its full text back to the clipboard.
- **Audio & Engine Status**: View active microphone input device at a glance.
- **Quit Application**: Easily quit the background engine directly from the menu.

---

## ⌨️ Shortcuts

### 1. Voice Dictation: Right Command (⌘)
- **Tap to Toggle:** Tap **Right ⌘** once to start recording, speak, then tap **Right ⌘** again to finish and paste.
- **Hold to Talk (Push-to-Talk):** Hold down **Right ⌘**, speak, and release when you're done.

### 2. Selected Text Corrector: Right Command + Option (⌘ + ⌥)
- **Proofread & Polish:** Select any text on screen in any application, then press **Right Command + Option**.
- **Smart In-Place Replacement:** If the text is in an editable field (text field, text area, code editor, browser input), it automatically replaces the selected text with the corrected version in-place!
- **Read-Only Safety:** If the selected text is in a read-only document or web page, it copies the corrected text to your clipboard without altering the screen.
- **Detailed Console Log:** Outputs a before/after comparison and performance metrics in the console.

---

## 🚀 Quick Setup & Launching

1. **Add your Gemini API Key:**
   Open `~/.config/dictation/.env` and add your key:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   ```

2. **Launch as a Native macOS App:**
   - Launch **`Gemini Assistant`** from **Spotlight (`⌘ + Space`)**, **Raycast**, **Launchpad**, or `~/Applications`.
   - *Optionally:* Add it to **System Settings > General > Login Items** to start automatically on login.
   - *Or run via Terminal:* `~/.config/dictation/run.sh`

3. **Start Dictating or Correcting:**
   - Press or hold **Right Command** to dictate.
   - Select text on screen and press **Right Command + Option** to polish and replace it.

4. **Logs & Privacy:**
   - Logs are stored in `~/.config/dictation/app.log`.
   - **Auto-Rotation:** Logs older than 24 hours (or larger than 2 MB) are automatically pruned on startup.
   - **Menu Bar Controls:** Click **"Open Logs..."** or **"Clear Logs"** anytime directly from the top menu bar (`🎙️`).

---

## ⚙️ Configuration (`.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model for speech-to-text transcription |
| `GEMINI_CORRECTOR_MODEL` | `gemini-3.5-flash-lite` | Gemini model for text correction and proofreading |
| `AUDIO_DEVICE` | `default` | Audio input device name (use `default` or e.g. `MacBook Pro Microphone`) |
| `HOTKEY` | `cmd_r` | Global hotkey trigger (`cmd_r`, `<ctrl>+<space>`, etc.) |
| `REPLACE_SELECTED_TEXT` | `true` | Automatically replaces selected text in-place when in editable fields |
| `PASTE_AUTOMATICALLY` | `true` | Auto-pastes transcribed text into the active app window |
| `ENABLE_HUD` | `true` | Shows native macOS floating HUD pill |
| `ENABLE_MENUBAR` | `true` | Shows native macOS menu bar (status item) icon in top panel |
| `HUD_STYLE` | `clear` | Glass translucency style (`regular` or `clear`) |
| `HUD_FOLLOW_CARET` | `true` | Floats the HUD next to the text caret (via Accessibility) instead of a fixed screen spot; needs Accessibility permission, falls back to the fixed spot otherwise |
| `ENABLE_SOUNDS` | `true` | Plays subtle macOS sound effects |
| `ENABLE_NOTIFICATIONS` | `true` | Shows a macOS notification banner when errors occur |
| `SILENCE_RMS_THRESHOLD` | `0.008` | RMS amplitude below which a recording is treated as silence/noise and skipped (no API call) |
| `MIN_SPEECH_DURATION` | `0.3` | Minimum recording length (seconds) to be considered speech |
| `DICTATION_LANGUAGES` | `English,Ukrainian` | Comma-separated languages the model should expect (narrows language detection) |
| `MIC_LEVEL_SCALE` | `4000` | Raw PCM RMS value that maps to a "full" HUD equalizer bar; lower it if your mic is quiet |

---

## 🎤 Audio Devices & CLI Flags

- **List Detected Microphones:**
  ```bash
  python3 main.py --list-devices
  ```
- **Run with a Specific Microphone:**
  ```bash
  python3 main.py --device "MacBook Pro Microphone"
  ```
- **Single Interactive Terminal Test:**
  ```bash
  python3 main.py --test
  ```

---

## 🔐 macOS Permissions

1. **Microphone Access:** macOS will request microphone permission when first recording.
2. **Accessibility Access:** For global key listening across all applications and reading selected text, make sure your terminal (Terminal / iTerm2) has permission enabled in:
   **System Settings > Privacy & Security > Accessibility**.


