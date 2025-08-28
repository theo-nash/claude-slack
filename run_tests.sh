#!/bin/bash

# Run tests for Claude-Slack API
# This script loads environment variables from .env file if present

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 Claude-Slack API Test Runner"
echo "================================"

# Find and load .env file
ENV_FILE=""
for path in ".env" "../.env" "../../.env" "$HOME/.env" "$HOME/at/.env"; do
    if [ -f "$path" ]; then
        ENV_FILE="$path"
        break
    fi
done

if [ -n "$ENV_FILE" ]; then
    echo "📋 Loading environment from: $ENV_FILE"
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "⚠️  No .env file found, using system environment"
fi

# Check for virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    # Try to activate venv if it exists
    if [ -d "$HOME/.venvs/claude-brain" ]; then
        echo "🐍 Activating virtual environment..."
        source "$HOME/.venvs/claude-brain/bin/activate"
    else
        echo "⚠️  No virtual environment active"
    fi
fi

# Install test dependencies if needed
echo "📦 Checking dependencies..."
pip install -q pytest pytest-asyncio pytest-cov python-dotenv 2>/dev/null || true

# Parse command line arguments
TEST_TYPE="${1:-all}"
VERBOSE=""
if [ "$2" = "-v" ] || [ "$2" = "--verbose" ]; then
    VERBOSE="-v"
fi

# Run appropriate tests
case "$TEST_TYPE" in
    unit)
        echo -e "\n${GREEN}Running unit tests...${NC}"
        pytest tests/api/test_sqlite_store.py tests/api/test_message_store.py $VERBOSE
        ;;
    integration)
        echo -e "\n${GREEN}Running integration tests...${NC}"
        pytest tests/api/test_unified_api.py $VERBOSE
        ;;
    qdrant)
        if [ -z "$QDRANT_URL" ] || [ -z "$QDRANT_API_KEY" ]; then
            echo -e "${RED}Error: Qdrant credentials not configured${NC}"
            echo "Please set QDRANT_URL and QDRANT_API_KEY in your .env file"
            exit 1
        fi
        echo -e "\n${GREEN}Running Qdrant integration tests...${NC}"
        pytest tests/api/test_qdrant_integration.py $VERBOSE
        ;;
    all)
        echo -e "\n${GREEN}Running all tests...${NC}"
        pytest tests/api/ $VERBOSE
        ;;
    coverage)
        echo -e "\n${GREEN}Running tests with coverage...${NC}"
        pytest tests/api/ --cov=api --cov-report=html --cov-report=term
        echo -e "\n${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    *)
        echo "Usage: $0 [unit|integration|qdrant|all|coverage] [-v]"
        echo ""
        echo "Options:"
        echo "  unit        - Run unit tests (SQLite, MessageStore)"
        echo "  integration - Run integration tests (UnifiedAPI)"
        echo "  qdrant      - Run Qdrant cloud tests (requires credentials)"
        echo "  all         - Run all tests (default)"
        echo "  coverage    - Run tests with coverage report"
        echo ""
        echo "  -v, --verbose - Verbose output"
        exit 1
        ;;
esac

# Check test results
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ Tests passed successfully!${NC}"
else
    echo -e "\n${RED}❌ Tests failed${NC}"
    exit 1
fi