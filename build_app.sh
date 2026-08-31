#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Gemini Assistant"
APP_BUNDLE="$DIR/$APP_NAME.app"
DEST_APP="$HOME/Applications/$APP_NAME.app"

echo "🔨 Building $APP_NAME.app..."

# 1. Ensure bundle directories
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
mkdir -p "$HOME/Applications"

# 2. Copy Info.plist and Icon
cp "$DIR/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"

cat << 'EOF' > "$APP_BUNDLE/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>Gemini Assistant</string>
    <key>CFBundleExecutable</key>
    <string>Gemini Assistant</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.gemini.dictation.assistant</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Gemini Assistant</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Gemini Assistant requires microphone access to dictate and transcribe speech.</string>
</dict>
</plist>
EOF

# 3. Compile native launcher binary
PYTHON_CONFIG=$(which python3.14-config || which python3.13-config || which python3.12-config || which python3-config)
CFLAGS=$($PYTHON_CONFIG --cflags --embed)
LDFLAGS=$($PYTHON_CONFIG --ldflags --embed)
PY_BASE_PREFIX=$(python3 -c "import sys; print(sys.base_prefix)" 2>/dev/null || echo "/opt/homebrew/opt/python@3.14/Frameworks/Python.framework/Versions/3.14")

clang -O2 $CFLAGS -DPYTHON_HOME_DIR="\"$PY_BASE_PREFIX\"" $LDFLAGS "$DIR/launcher.c" -o "$APP_BUNDLE/Contents/MacOS/$APP_NAME"

# 4. Sign and install to ~/Applications
codesign --force --deep --sign - -r='designated => identifier "com.gemini.dictation.assistant"' "$APP_BUNDLE"
rm -rf "$DEST_APP"
cp -R "$APP_BUNDLE" "$HOME/Applications/"
codesign --force --deep --sign - -r='designated => identifier "com.gemini.dictation.assistant"' "$DEST_APP"

echo "✅ $APP_NAME.app built and installed to ~/Applications/$APP_NAME.app"
