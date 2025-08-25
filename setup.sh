#!/bin/bash

echo "🚶‍♂️ Privilege Walk Application Setup"
echo "======================================"
echo ""

# Check if UV is installed
if ! command -v uv &> /dev/null; then
    echo "❌ UV is not installed. Please install UV first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   or visit: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

echo "✅ UV is installed"

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Please run this script from the project directory"
    exit 1
fi

echo "✅ Project directory found"

# Sync the UV environment
echo "📦 Syncing UV environment..."
uv sync

if [ $? -eq 0 ]; then
    echo "✅ UV environment is ready!"
    echo ""
    echo "🚀 You can now run the application with:"
    echo "   ./run.sh"
    echo "   or"
    echo "   uv run python run.py"
    echo ""
    echo "📱 The application will be available at: http://localhost:5001"
else
    echo "❌ Failed to sync UV environment"
    exit 1
fi 