#!/usr/bin/env bash
# ==============================================================================
# Game Poster Studio v2.0 — Linux Server Automated Setup Script
# Supports Lite (default, <15MB, zero X11) and Pro (--pro, 4GB RAM AI Edition)
# ==============================================================================

set -e

PRO_MODE=false
for arg in "$@"; do
    if [ "$arg" = "--pro" ]; then
        PRO_MODE=true
    fi
done

echo "🎮 Setting up Game Poster Studio v2.0 on Linux Server..."

if ! command -v python3 &>/dev/null; then
    echo "❌ Error: Python 3 is required but not installed." >&2
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Detected Python version: $PY_VERSION"

if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment (venv)..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "📥 Installing Game Poster Studio Lite (Pillow + NumPy + CLI entrypoints)..."
pip install --upgrade pip --quiet
pip install -e . --quiet

if [ "$PRO_MODE" = true ]; then
    echo "🧠 Installing Game Poster Studio Pro AI Plugin (4GB RAM CPU-Safe Edition)..."
    pip install -e ./poster_studio_pro --quiet
fi

echo "🧪 Running headless self-test..."
python3 cli.py --input examples/raw_cover.jpg --output test_verify.jpg --ratio 4:5 --preset cyberpunk --watermark "BAZYEPC"

if [ -f "test_verify.jpg" ]; then
    rm -f test_verify.jpg
    echo "========================================================"
    echo "🎉 SUCCESS: Game Poster Studio v2.0 is 100% operational!"
    echo "========================================================"
    echo "Usage Examples:"
    echo "  1. CLI:        poster-studio -i cover.jpg -o poster.jpg --preset cyberpunk"
    echo "  2. Collage:    poster-studio --collage c1.jpg c2.jpg c3.jpg --template trilogy -o out.jpg"
    echo "  3. Bot:        BOT_TOKEN=... poster-studio-bot"
    echo "  4. Agent Docs: See skills/game-poster-studio/SKILL.md"
    echo "========================================================"
else
    echo "❌ Self-test failed to produce output image." >&2
    exit 1
fi
