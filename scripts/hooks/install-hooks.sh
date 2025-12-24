#!/bin/bash
# Install git hooks for Mind Palace
# Run: ./scripts/hooks/install-hooks.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

echo "Installing Mind Palace git hooks..."

# Make hook scripts executable
chmod +x "$SCRIPT_DIR/post-commit-palace-sync.sh"
chmod +x "$SCRIPT_DIR/post-merge-palace-viz.sh"

# Install post-commit hook
if [ -f "$HOOKS_DIR/post-commit" ]; then
    # Append to existing hook if not already there
    if ! grep -q "post-commit-palace-sync" "$HOOKS_DIR/post-commit" 2>/dev/null; then
        echo "" >> "$HOOKS_DIR/post-commit"
        echo "# Mind Palace sync" >> "$HOOKS_DIR/post-commit"
        echo "$SCRIPT_DIR/post-commit-palace-sync.sh" >> "$HOOKS_DIR/post-commit"
        echo "  Added palace sync to existing post-commit hook"
    else
        echo "  post-commit: Palace sync already installed"
    fi
else
    cat > "$HOOKS_DIR/post-commit" << EOF
#!/bin/bash
# Run Mind Palace sync on commit
$SCRIPT_DIR/post-commit-palace-sync.sh
EOF
    chmod +x "$HOOKS_DIR/post-commit"
    echo "  Installed post-commit hook"
fi

# Install post-merge hook
if [ -f "$HOOKS_DIR/post-merge" ]; then
    if ! grep -q "post-merge-palace-viz" "$HOOKS_DIR/post-merge" 2>/dev/null; then
        echo "" >> "$HOOKS_DIR/post-merge"
        echo "# Mind Palace visualization update" >> "$HOOKS_DIR/post-merge"
        echo "$SCRIPT_DIR/post-merge-palace-viz.sh" >> "$HOOKS_DIR/post-merge"
        echo "  Added palace viz to existing post-merge hook"
    else
        echo "  post-merge: Palace viz already installed"
    fi
else
    cat > "$HOOKS_DIR/post-merge" << EOF
#!/bin/bash
# Regenerate Mind Palace visualization on merge to main
$SCRIPT_DIR/post-merge-palace-viz.sh
EOF
    chmod +x "$HOOKS_DIR/post-merge"
    echo "  Installed post-merge hook"
fi

echo ""
echo "Done! Hooks installed:"
echo "  - post-commit: Quick drift check on backend changes"
echo "  - post-merge: Full rebuild + visualization on merge to main"
