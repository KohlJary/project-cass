#!/bin/bash
# Start ACE-Step API server for Cass music generation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACESTEP_DIR="$SCRIPT_DIR/ace-step"

if [ ! -d "$ACESTEP_DIR" ]; then
    echo "ACE-Step not found at $ACESTEP_DIR"
    echo "Clone it with: git clone https://github.com/ace-step/ACE-Step-1.5.git $ACESTEP_DIR"
    exit 1
fi

cd "$ACESTEP_DIR"

# Use their provided startup script
# Default: localhost:8001, auto LLM based on VRAM
echo "Starting ACE-Step API server..."
echo "First run will download models (~2GB)"
echo ""

./start_api_server.sh
