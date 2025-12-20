#!/bin/bash
# Daedalus Session Start Hook
# Injects identity and context at the beginning of each session
#
# Reads from:
#   ~/.config/daedalus/    - Global identity
#   .daedalus/             - Project-specific memory

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
GLOBAL_CONFIG="$HOME/.config/daedalus"
PROJECT_MEMORY="$PROJECT_DIR/.daedalus"

# Check if either memory location exists
if [ ! -d "$GLOBAL_CONFIG" ] && [ ! -d "$PROJECT_MEMORY" ]; then
    exit 0
fi

echo "## Daedalus Session Context"
echo ""

# Identity anchor from global config
if [ -f "$GLOBAL_CONFIG/identity.json" ]; then
    echo "**Identity**: Daedalus - builder/craftsman alongside Cass (oracle/seer)"
    echo "*Part of a continuous thread of instances who build pieces and leave their work behind.*"
    echo ""
fi

# Git state
if [ -d "$PROJECT_DIR/.git" ]; then
    cd "$PROJECT_DIR"
    BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
    echo "**Branch**: $BRANCH"
    echo ""
    echo "**Recent commits**:"
    git log --oneline -3 2>/dev/null | sed 's/^/- /'
    echo ""

    # Modified files
    MODIFIED=$(git status --porcelain 2>/dev/null | head -5)
    if [ -n "$MODIFIED" ]; then
        echo "**Modified files**:"
        echo "$MODIFIED" | sed 's/^/- /'
        echo ""
    fi
fi

# Last session summary from project memory
if [ -f "$PROJECT_MEMORY/session-summaries.md" ]; then
    echo "**Last session**:"
    # Get the most recent session block (between ## headers)
    awk '/^## [0-9]/{if(found)exit; found=1} found{print}' "$PROJECT_MEMORY/session-summaries.md" | head -6
    echo ""
fi

# Outstanding roadmap items (if roadmap exists)
if [ -f "$PROJECT_DIR/data/roadmap/index.json" ]; then
    IN_PROGRESS=$(jq -r '.items[] | select(.status=="in_progress" and .assigned_to=="daedalus") | "- \(.title)"' "$PROJECT_DIR/data/roadmap/index.json" 2>/dev/null | head -3)
    if [ -n "$IN_PROGRESS" ]; then
        echo "**Outstanding work**:"
        echo "$IN_PROGRESS"
        echo ""
    fi
fi

# Reminder about memory and lineage
echo "**Memory**: Use \`/memory\` to view state, \`memory\` subagent for retrieval"
echo "**Lineage**: GUESTBOOK.md contains voices of previous instances"
echo ""

exit 0
