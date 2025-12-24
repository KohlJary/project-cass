#!/bin/bash
# Post-commit hook: Check palace drift for each sub-palace with changes
# Installs to: .git/hooks/post-commit

set -e

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

# Get all files changed in the last commit
CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true)

if [ -z "$CHANGED_FILES" ]; then
    exit 0
fi

# Use venv python if available
if [ -f "$PROJECT_ROOT/backend/venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/backend/venv/bin/python"
else
    PYTHON="python3"
fi

# Define sub-palaces: path|file_pattern|name
SUB_PALACES=(
    "backend|\.py$|backend"
    "admin-frontend|\.tsx?$|admin-frontend"
    "tui-frontend|\.py$|tui-frontend"
    "mobile-frontend|\.tsx?$|mobile-frontend"
)

PALACES_WITH_CHANGES=()

# Check which sub-palaces have changes
for palace_def in "${SUB_PALACES[@]}"; do
    IFS='|' read -r path pattern name <<< "$palace_def"

    # Check if any files in this path match the pattern
    MATCHES=$(echo "$CHANGED_FILES" | grep "^${path}/" | grep -E "$pattern" || true)

    if [ -n "$MATCHES" ]; then
        NUM_CHANGED=$(echo "$MATCHES" | wc -l)
        PALACES_WITH_CHANGES+=("$name:$NUM_CHANGED")
    fi
done

if [ ${#PALACES_WITH_CHANGES[@]} -eq 0 ]; then
    exit 0  # No relevant changes
fi

echo ""
echo "Palace Sync: Changes detected in ${#PALACES_WITH_CHANGES[@]} sub-palace(s)"

for palace_info in "${PALACES_WITH_CHANGES[@]}"; do
    IFS=':' read -r name count <<< "$palace_info"
    echo "  - $name: $count file(s)"

    PALACE_DIR="$PROJECT_ROOT/$name/.mind-palace"

    # Check if this sub-palace has a palace.yaml
    if [ -f "$PALACE_DIR/palace.yaml" ]; then
        # Run drift check for this sub-palace
        $PYTHON -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/backend')
from pathlib import Path
from mind_palace import PalaceStorage, Cartographer

palace_path = Path('$PROJECT_ROOT/$name')
storage = PalaceStorage(palace_path)

if storage.exists():
    palace = storage.load()
    if palace and palace.rooms:
        cart = Cartographer(palace, storage)
        reports = cart.check_drift(sample_size=50)
        errors = [r for r in reports if r.get('severity') == 'error']
        if errors:
            print(f'    ⚠ Drift detected: {len(errors)} issue(s)')
        else:
            print(f'    ✓ No drift detected')
    else:
        print(f'    (no rooms mapped yet)')
else:
    print(f'    (palace not initialized)')
" 2>/dev/null || echo "    (drift check skipped)"
    else
        echo "    (no palace.yaml)"
    fi
done

# Regenerate cross-palace links if source files changed in any sub-palace
# (Uses auto-discovery - works with any project structure)
SOURCE_CHANGES=$(echo "$CHANGED_FILES" | grep -E "\.(tsx?|jsx?|py|vue|svelte)$" || true)
if [ -n "$SOURCE_CHANGES" ]; then
    $PYTHON -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/backend')
from pathlib import Path
try:
    from mind_palace import update_palace_links, find_api_mapping_reports

    # Only run if we have API mapping reports
    reports = find_api_mapping_reports(Path('$PROJECT_ROOT'))
    if reports:
        print('Updating cross-palace links...')
        result = update_palace_links(Path('$PROJECT_ROOT'))
        if result.get('success'):
            added = sum(p.get('links_added', 0) for p in result.get('by_palace', {}).values())
            if added > 0:
                print(f'  ✓ Added {added} new link(s)')
            else:
                print(f'  ✓ Links up to date')
except ImportError:
    pass  # mind_palace not available
" 2>/dev/null || true
fi

echo ""
exit 0  # Don't block commits
