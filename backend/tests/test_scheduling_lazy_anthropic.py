"""
Issue #46: importing the scheduling package must not need the anthropic SDK.
decision_engine imported it at module load, and scheduling/__init__ imports
decision_engine, so `import scheduling.day_phase` failed without the SDK.
"""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# Block anthropic with a meta-path finder, then import scheduling.day_phase
# in a fresh interpreter so nothing is already cached.
_SCRIPT = """
import sys

class _Block:
    def find_spec(self, name, path=None, target=None):
        if name == "anthropic" or name.startswith("anthropic."):
            raise ModuleNotFoundError("No module named 'anthropic' (blocked)")
        return None

sys.meta_path.insert(0, _Block())
import scheduling.day_phase  # noqa: F401
import scheduling  # noqa: F401
assert "anthropic" not in sys.modules
print("ok")
"""


def test_scheduling_imports_without_anthropic():
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().endswith("ok")
