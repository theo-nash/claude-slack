#!/bin/bash
# Start the Claude-Slack API Server

echo "🚀 Starting Claude-Slack API Server..."

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists in parent directory
if [ ! -d "../.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv ../.venv
fi

# Activate virtual environment
source ../.venv/bin/activate

# Install requirements if needed
echo "Checking dependencies..."
pip install -q -r requirements.txt

# Start the FastAPI server
echo "Starting server on http://localhost:8000"
echo "API docs available at http://localhost:8000/docs"
echo "Press Ctrl+C to stop"
echo ""

# Run with uvicorn for production-like performance
uvicorn api_server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info