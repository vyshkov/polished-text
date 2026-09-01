#!/usr/bin/env bash
set -e

# Change to workspace directory
cd "$(dirname "$0")"

# Locate ruff binary
if [ -x "./venv/bin/ruff" ]; then
    RUFF="./venv/bin/ruff"
elif command -v ruff &> /dev/null; then
    RUFF="ruff"
else
    echo "❌ Error: 'ruff' not found. Please install with: pip install -r requirements-dev.txt"
    exit 1
fi

if [[ "$1" == "--fix" || "$1" == "-f" ]]; then
    echo "🔧 Running Ruff auto-fix and format..."
    "$RUFF" check --fix dictation_app main.py
    "$RUFF" format dictation_app main.py
    echo "✅ Formatting & auto-fixing completed!"
else
    echo "🔍 Running Ruff linter..."
    "$RUFF" check dictation_app main.py
    echo "🔍 Checking code formatting..."
    "$RUFF" format --check dictation_app main.py
    echo "✅ All linting and formatting checks passed!"
fi
