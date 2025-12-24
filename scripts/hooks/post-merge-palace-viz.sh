#!/bin/bash
# Post-merge hook: Regenerate all sub-palace data and visualization on main
# Installs to: .git/hooks/post-merge

set -e

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

# Only run on main branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    exit 0
fi

echo ""
echo "Palace Update: Merged to main, regenerating all palaces..."

# Use venv python if available
if [ -f "$PROJECT_ROOT/backend/venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/backend/venv/bin/python"
else
    PYTHON="python3"
fi

# Define sub-palaces to rebuild
SUB_PALACES=("backend" "admin-frontend" "tui-frontend" "mobile-frontend")

for name in "${SUB_PALACES[@]}"; do
    PALACE_DIR="$PROJECT_ROOT/$name/.mind-palace"

    if [ -f "$PALACE_DIR/palace.yaml" ]; then
        echo "  Rebuilding $name palace..."

        $PYTHON -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/backend')
from pathlib import Path
from mind_palace import PalaceStorage, Cartographer

palace_path = Path('$PROJECT_ROOT/$name')
storage = PalaceStorage(palace_path)

if storage.exists():
    palace = storage.load()
    if palace:
        cart = Cartographer(palace, storage)
        # Map the directory
        regions, buildings, rooms = cart.map_directory(palace_path, recursive=True)
        storage.save(palace)
        print(f'    Mapped: {buildings} buildings, {rooms} rooms')
" 2>/dev/null || echo "    (rebuild skipped - no palace infrastructure)"
    fi
done

# Generate combined visualization from root meta-palace
echo "  Generating codebase visualization..."
$PYTHON -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/backend')
from pathlib import Path
from mind_palace import PalaceStorage, Cartographer

# Use root meta-palace
storage = PalaceStorage(Path('$PROJECT_ROOT'))
palace = storage.load()
if palace:
    cart = Cartographer(palace, storage)

    # Export call graph for backend (main code)
    cart.export_graph_json(
        Path('$PROJECT_ROOT/backend'),
        Path('$PROJECT_ROOT/.mind-palace/codebase-graph.json')
    )
    print('    Exported: .mind-palace/codebase-graph.json')

    # Generate HTML visualization
    cart.visualize_html(
        Path('$PROJECT_ROOT/backend'),
        Path('$PROJECT_ROOT/.mind-palace/codebase-viz.html')
    )
    print('    Generated: .mind-palace/codebase-viz.html')
" 2>/dev/null || echo "    (visualization generation failed)"

echo "  Palace update complete!"
echo ""

exit 0
