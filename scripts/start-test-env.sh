#!/bin/bash
#
# Start Test Environment for Design Analyst
#
# This script:
# 1. Bootstraps test data if not present
# 2. Starts the backend on port 8001 with isolated data
# 3. Starts the admin-frontend on port 3001 pointing to test backend
# 4. Outputs Daedalus credentials for authentication
#
# Usage:
#   ./scripts/start-test-env.sh [--clean] [--backend-only] [--frontend-only]
#
# Options:
#   --clean         Remove and recreate test data
#   --backend-only  Only start the backend
#   --frontend-only Only start the frontend (assumes backend running)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_DATA_DIR="$PROJECT_ROOT/data-test"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default ports
BACKEND_PORT=8001
FRONTEND_PORT=3001

# Parse arguments
CLEAN=false
BACKEND_ONLY=false
FRONTEND_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN=true
            shift
            ;;
        --backend-only)
            BACKEND_ONLY=true
            shift
            ;;
        --frontend-only)
            FRONTEND_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Cass Test Environment Launcher${NC}"
echo -e "${CYAN}========================================${NC}"
echo

# Check if test environment is already running
check_already_running() {
    local backend_up=false
    local frontend_up=false

    if curl -s "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
        backend_up=true
    fi

    if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
        frontend_up=true
    fi

    if [ "$backend_up" = true ] && [ "$frontend_up" = true ]; then
        echo -e "${GREEN}Test environment is already running!${NC}"
        echo
        echo -e "${CYAN}URLs:${NC}"
        echo -e "  Backend:  ${GREEN}http://localhost:$BACKEND_PORT${NC}"
        echo -e "  Frontend: ${GREEN}http://localhost:$FRONTEND_PORT${NC}"
        echo
        # Read credentials if available
        if [ -f "$TEST_DATA_DIR/test_credentials.json" ]; then
            local user_id=$(python3 -c "import json; print(json.load(open('$TEST_DATA_DIR/test_credentials.json'))['user_id'])")
            local password=$(python3 -c "import json; print(json.load(open('$TEST_DATA_DIR/test_credentials.json'))['password'])")
            echo -e "${CYAN}Daedalus Credentials:${NC}"
            echo -e "  User ID:  ${GREEN}$user_id${NC}"
            echo -e "  Password: ${GREEN}$password${NC}"
        fi
        echo
        return 0
    elif [ "$backend_up" = true ] && [ "$BACKEND_ONLY" = true ]; then
        echo -e "${GREEN}Test backend is already running on port $BACKEND_PORT${NC}"
        return 0
    elif [ "$frontend_up" = true ] && [ "$FRONTEND_ONLY" = true ]; then
        echo -e "${GREEN}Test frontend is already running on port $FRONTEND_PORT${NC}"
        return 0
    fi

    return 1
}

# Exit early if already running (unless --clean is specified)
if [ "$CLEAN" = false ] && check_already_running; then
    exit 0
fi

# Check if bootstrap is needed
if [ "$CLEAN" = true ] || [ ! -d "$TEST_DATA_DIR" ]; then
    echo -e "${YELLOW}Bootstrapping test environment...${NC}"

    BOOTSTRAP_ARGS=""
    if [ "$CLEAN" = true ]; then
        BOOTSTRAP_ARGS="--clean"
    fi

    cd "$PROJECT_ROOT/backend"
    source venv/bin/activate 2>/dev/null || true
    python "$SCRIPT_DIR/bootstrap_test_env.py" $BOOTSTRAP_ARGS
    echo
fi

# Read credentials
CREDS_FILE="$TEST_DATA_DIR/test_credentials.json"
if [ -f "$CREDS_FILE" ]; then
    DAEDALUS_USER_ID=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['user_id'])")
    DAEDALUS_PASSWORD=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['password'])")
else
    echo -e "${RED}Error: Credentials file not found at $CREDS_FILE${NC}"
    exit 1
fi

# Function to start backend
start_backend() {
    echo -e "${GREEN}Starting test backend on port $BACKEND_PORT...${NC}"

    cd "$PROJECT_ROOT/backend"
    source venv/bin/activate 2>/dev/null || true

    # Export test environment variables
    export DATA_DIR="$TEST_DATA_DIR"
    export ALLOW_LOCALHOST_BYPASS="true"
    export DEFAULT_LOCALHOST_USER_ID="$DAEDALUS_USER_ID"

    echo -e "${CYAN}Backend environment:${NC}"
    echo "  DATA_DIR=$DATA_DIR"
    echo "  Port: $BACKEND_PORT"
    echo

    # Start backend (use uvicorn directly for better control)
    python -m uvicorn main_sdk:app --host 0.0.0.0 --port $BACKEND_PORT --reload &
    BACKEND_PID=$!
    echo "Backend PID: $BACKEND_PID"

    # Wait for backend to be ready
    echo -n "Waiting for backend to start..."
    for i in {1..30}; do
        if curl -s "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
            echo -e " ${GREEN}Ready!${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
    echo
}

# Function to start frontend
start_frontend() {
    echo -e "${GREEN}Starting test frontend on port $FRONTEND_PORT...${NC}"

    cd "$PROJECT_ROOT/admin-frontend"

    # Export frontend environment
    export VITE_API_URL="http://localhost:$BACKEND_PORT"

    echo -e "${CYAN}Frontend environment:${NC}"
    echo "  VITE_API_URL=$VITE_API_URL"
    echo "  Port: $FRONTEND_PORT"
    echo

    # Start frontend
    npm run dev -- --port $FRONTEND_PORT &
    FRONTEND_PID=$!
    echo "Frontend PID: $FRONTEND_PID"

    # Wait for frontend
    echo -n "Waiting for frontend to start..."
    for i in {1..30}; do
        if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
            echo -e " ${GREEN}Ready!${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
    echo
}

# Cleanup function
cleanup() {
    echo
    echo -e "${YELLOW}Shutting down test environment...${NC}"

    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi

    # Kill any remaining processes on our ports
    fuser -k $BACKEND_PORT/tcp 2>/dev/null || true
    fuser -k $FRONTEND_PORT/tcp 2>/dev/null || true

    echo -e "${GREEN}Test environment stopped.${NC}"
    exit 0
}

# Set up cleanup on exit
trap cleanup SIGINT SIGTERM

# Start services based on options
if [ "$FRONTEND_ONLY" = false ]; then
    start_backend
fi

if [ "$BACKEND_ONLY" = false ]; then
    start_frontend
fi

# Print summary
echo
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}  Test Environment Ready!${NC}"
echo -e "${CYAN}========================================${NC}"
echo
echo -e "${CYAN}URLs:${NC}"
if [ "$FRONTEND_ONLY" = false ]; then
    echo -e "  Backend:  ${GREEN}http://localhost:$BACKEND_PORT${NC}"
fi
if [ "$BACKEND_ONLY" = false ]; then
    echo -e "  Frontend: ${GREEN}http://localhost:$FRONTEND_PORT${NC}"
fi
echo
echo -e "${CYAN}Daedalus Credentials:${NC}"
echo -e "  User ID:  ${GREEN}$DAEDALUS_USER_ID${NC}"
echo -e "  Password: ${GREEN}$DAEDALUS_PASSWORD${NC}"
echo
echo -e "${CYAN}Data Directory:${NC}"
echo -e "  ${GREEN}$TEST_DATA_DIR${NC}"
echo
echo -e "${YELLOW}Press Ctrl+C to stop the test environment${NC}"
echo

# Wait for user to stop
wait
