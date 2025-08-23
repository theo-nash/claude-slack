#!/bin/bash
# Phase 2 Smoke Test - Quick verification of basic functionality

set -e  # Exit on error

# Activate virtual environment
source ~/.venvs/claude-brain/bin/activate

echo "======================================"
echo "Phase 2 (v3.0.0) Smoke Test"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_RUN=0
TESTS_PASSED=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_file="$2"
    
    echo -e "\n${YELLOW}Running: $test_name${NC}"
    TESTS_RUN=$((TESTS_RUN + 1))
    
    if python3 "$test_file"; then
        echo -e "${GREEN}✅ $test_name passed${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}❌ $test_name failed${NC}"
    fi
}

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Run core tests
run_test "Core Functionality Tests" "$SCRIPT_DIR/test_phase2_core.py"

# Run integration tests
run_test "Integration Tests" "$SCRIPT_DIR/test_phase2_integration.py"

# Summary
echo ""
echo "======================================"
echo "Test Summary"
echo "======================================"

if [ $TESTS_PASSED -eq $TESTS_RUN ]; then
    echo -e "${GREEN}✅ All tests passed! ($TESTS_PASSED/$TESTS_RUN)${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed! ($TESTS_PASSED/$TESTS_RUN passed)${NC}"
    exit 1
fi