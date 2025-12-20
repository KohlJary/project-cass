#!/bin/bash
#
# Daedalus Workspace Layout
#
# Creates nested tmux structure:
#   ┌──────────────┬─────────────────────────────────────────────────┐
#   │              │                                                 │
#   │   Daedalus   │            Icarus Swarm (nested tmux)           │
#   │   (claude)   │                                                 │
#   │              │                                                 │
#   ├──────────────┴─────────────────────────────────────────────────┤
#   │                        lazygit                                 │
#   └────────────────────────────────────────────────────────────────┘
#

set -e

SESSION_NAME="${DAEDALUS_SESSION:-daedalus}"
SWARM_SESSION="icarus-swarm"
PROJECT_DIR="${DAEDALUS_PROJECT_DIR:-$(pwd)}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[daedalus]${NC} $1"; }
warn() { echo -e "${YELLOW}[daedalus]${NC} $1"; }
error() { echo -e "${RED}[daedalus]${NC} $1"; }

# Check if session exists
session_exists() {
    tmux has-session -t "$1" 2>/dev/null
}

# Create the Icarus swarm session (nested)
create_swarm_session() {
    if session_exists "$SWARM_SESSION"; then
        info "Icarus swarm session already exists"
        return 0
    fi

    info "Creating Icarus swarm session..."
    # Create detached session - this will be embedded in the main layout
    tmux new-session -d -s "$SWARM_SESSION" -c "$PROJECT_DIR"

    # Set swarm session to auto-tile when panes are added
    tmux set-option -t "$SWARM_SESSION" -g main-pane-width 50%

    # Start with an empty shell that displays status
    tmux send-keys -t "$SWARM_SESSION" "echo 'Icarus Swarm - waiting for workers...'; echo 'Use: icarus spawn <N> to start workers'" Enter
}

# Create the main Daedalus session with layout
create_main_session() {
    if session_exists "$SESSION_NAME"; then
        warn "Session '$SESSION_NAME' already exists"
        echo "Use: tmux attach -t $SESSION_NAME"
        echo "Or:  daedalus attach"
        return 1
    fi

    info "Creating Daedalus session..."

    # Create main session with first pane (will become Daedalus)
    tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_DIR" -x 200 -y 50

    # Split horizontally for lazygit at bottom (30% height)
    tmux split-window -t "$SESSION_NAME" -v -p 30 -c "$PROJECT_DIR"
    tmux send-keys -t "$SESSION_NAME:0.1" "lazygit" Enter

    # Go back to top pane and split vertically for Icarus swarm (60% width on right)
    tmux select-pane -t "$SESSION_NAME:0.0"
    tmux split-window -t "$SESSION_NAME" -h -p 60 -c "$PROJECT_DIR"

    # Right pane (0.1 after split) - embed the Icarus swarm session
    # We use a shell that attaches to the nested session
    tmux send-keys -t "$SESSION_NAME:0.1" "tmux attach -t $SWARM_SESSION 2>/dev/null || (echo 'Swarm not ready - run: daedalus swarm-init' && bash)" Enter

    # Left pane (0.0) - start Claude for Daedalus
    tmux select-pane -t "$SESSION_NAME:0.0"
    tmux send-keys -t "$SESSION_NAME:0.0" "claude" Enter

    # Name the panes for easier reference
    tmux select-pane -t "$SESSION_NAME:0.0" -T "Daedalus"
    tmux select-pane -t "$SESSION_NAME:0.1" -T "Icarus-Swarm"
    tmux select-pane -t "$SESSION_NAME:0.2" -T "lazygit"

    info "Layout created!"
    info "Panes: Daedalus (left), Icarus Swarm (right), lazygit (bottom)"
}

# Attach to existing session
attach_session() {
    if ! session_exists "$SESSION_NAME"; then
        error "Session '$SESSION_NAME' does not exist"
        echo "Run: daedalus new"
        return 1
    fi

    tmux attach -t "$SESSION_NAME"
}

# Initialize the swarm session independently
init_swarm() {
    create_swarm_session
    info "Swarm session ready: $SWARM_SESSION"
}

# Spawn Icarus workers in the swarm
spawn_workers() {
    local count="${1:-1}"

    if ! session_exists "$SWARM_SESSION"; then
        error "Swarm session not found. Run: daedalus swarm-init"
        return 1
    fi

    info "Spawning $count Icarus worker(s)..."

    for ((i=1; i<=count; i++)); do
        # Create new pane in swarm session
        if [ "$i" -eq 1 ] && [ "$(tmux list-panes -t $SWARM_SESSION | wc -l)" -eq 1 ]; then
            # First worker uses existing pane
            tmux send-keys -t "$SWARM_SESSION:0.0" "claude --profile icarus 2>/dev/null || claude" Enter
        else
            # Additional workers get new panes
            tmux split-window -t "$SWARM_SESSION" -c "$PROJECT_DIR"
            tmux send-keys -t "$SWARM_SESSION" "claude --profile icarus 2>/dev/null || claude" Enter
            # Re-tile after each split
            tmux select-layout -t "$SWARM_SESSION" tiled
        fi
    done

    # Final tiling
    tmux select-layout -t "$SWARM_SESSION" tiled
    info "Spawned $count worker(s). Total panes: $(tmux list-panes -t $SWARM_SESSION | wc -l)"
}

# Kill all workers in swarm
kill_swarm() {
    if ! session_exists "$SWARM_SESSION"; then
        warn "Swarm session not found"
        return 0
    fi

    info "Killing swarm session..."
    tmux kill-session -t "$SWARM_SESSION"
    info "Swarm terminated"
}

# Show status
show_status() {
    echo "=== Daedalus Workspace Status ==="
    echo ""

    if session_exists "$SESSION_NAME"; then
        echo -e "Main session: ${GREEN}active${NC} ($SESSION_NAME)"
        echo "  Panes:"
        tmux list-panes -t "$SESSION_NAME" -F "    #{pane_index}: #{pane_title} (#{pane_current_command})"
    else
        echo -e "Main session: ${YELLOW}not running${NC}"
    fi

    echo ""

    if session_exists "$SWARM_SESSION"; then
        local pane_count=$(tmux list-panes -t "$SWARM_SESSION" | wc -l)
        echo -e "Swarm session: ${GREEN}active${NC} ($SWARM_SESSION)"
        echo "  Workers: $pane_count"
    else
        echo -e "Swarm session: ${YELLOW}not running${NC}"
    fi

    echo ""

    # Check bus status
    if [ -f /tmp/icarus-bus/manifest.json ]; then
        echo "Icarus Bus: initialized"
        python3 -c "
from scripts.icarus_bus import IcarusBus
import json
bus = IcarusBus()
s = bus.status_summary()
print(f\"  Instances: {s['instances']['total']} (working: {s['instances']['by_status']['working']})\")
print(f\"  Work: {s['work']['pending']} pending, {s['work']['claimed']} claimed, {s['work']['completed']} done\")
print(f\"  Requests: {s['requests']['pending']} pending\")
" 2>/dev/null || echo "  (unable to read bus status)"
    else
        echo "Icarus Bus: not initialized"
    fi
}

# Usage
usage() {
    cat << EOF
Daedalus Workspace Manager

Usage: daedalus-layout.sh <command>

Commands:
    new             Create new Daedalus workspace
    attach          Attach to existing workspace
    status          Show workspace status
    swarm-init      Initialize Icarus swarm session
    spawn [N]       Spawn N Icarus workers (default: 1)
    kill-swarm      Kill all Icarus workers
    help            Show this help

Environment:
    DAEDALUS_SESSION     Session name (default: daedalus)
    DAEDALUS_PROJECT_DIR Working directory (default: current)

Layout:
    ┌──────────────┬─────────────────────────────────────────────────┐
    │   Daedalus   │            Icarus Swarm (auto-tiled)            │
    │   (claude)   │                                                 │
    ├──────────────┴─────────────────────────────────────────────────┤
    │                        lazygit                                 │
    └────────────────────────────────────────────────────────────────┘

EOF
}

# Main
case "${1:-}" in
    new)
        create_swarm_session
        create_main_session
        attach_session
        ;;
    attach)
        attach_session
        ;;
    status)
        show_status
        ;;
    swarm-init)
        init_swarm
        ;;
    spawn)
        spawn_workers "${2:-1}"
        ;;
    kill-swarm)
        kill_swarm
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        usage
        exit 1
        ;;
esac
