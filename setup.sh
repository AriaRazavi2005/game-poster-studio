#!/usr/bin/env bash
# ==============================================================================
# Game Poster Studio — Linux Server Automated Setup Script
# For headless deployment in Telegram automation bots (@BazyePc)
# ==============================================================================

set -e

echo "🎮 Setting up Game Poster Studio on Linux Server..."

# 1. Verify Python 3
if ! command -v python3 &>/dev/null; then
    echo "❌ Error: Python 3 is required but not installed." >&2
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Detected Python version: $PY_VERSION"

# 2. Setup virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# 3. Upgrade pip and install core headless dependencies
echo "📥 Installing dependencies (Pillow, NumPy)..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# 4. Verify headless execution with self-test
echo "🧪 Running headless self-test..."
python3 cli.py --input examples/raw_cover.jpg --output test_verify.jpg --ratio 4:5 --margin 45 --curve 40 --watermark "BAZYEPC"

if [ -f "test_verify.jpg" ]; then
    rm -f test_verify.jpg
    echo "========================================================"
    echo "🎉 SUCCESS: Game Poster Studio is 100% operational!"
    echo "========================================================"
    echo "Usage Examples:"
    echo "  1. CLI:        python cli.py --input cover.jpg --output poster.jpg --ratio 4:5"
    echo "  2. Batch:      python cli.py --batch-dir ./raw_covers/ --output ./ready/"
    echo "  3. Python API: from telegram_bridge import create_game_poster"
    echo "  4. Agent Docs: See skills/game-poster-studio/SKILL.md"
    echo "========================================================"
else
    echo "❌ Self-test failed to produce output image." >&2
    exit 1
fi
