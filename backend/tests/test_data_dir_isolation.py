"""Nothing writes under the checkout's data directories when DATA_DIR points
elsewhere (#105). Isolated runs (tests, benchmarks) depend on it."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
ROOTS = [BACKEND / "data", BACKEND.parent / "data"]


def _listing(root: Path):
    if not root.exists():
        return None
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if not root.is_symlink() else "symlink"


@pytest.mark.slow
def test_importing_the_app_leaves_checkout_data_alone(tmp_path):
    pytest.importorskip("multipart")
    if any(r.is_symlink() for r in ROOTS):
        pytest.skip("checkout data is a symlink to real data; run from a worktree or CI")
    before = {r: _listing(r) for r in ROOTS}
    env = {**os.environ, "DATA_DIR": str(tmp_path / "data"), "CASS_PROFILE": "test"}
    proc = subprocess.run([sys.executable, "-c", "import main_sdk"], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    after = {r: _listing(r) for r in ROOTS}
    assert after == before, {str(r): (before[r], after[r]) for r in ROOTS if before[r] != after[r]}


@pytest.mark.unit
def test_default_dirs_live_under_data_dir(monkeypatch):
    """The sites that only build their path on use (constructors), which the
    import test above can't reach."""
    import config
    root = Path(config.DATA_DIR).resolve()

    def under(p):
        return Path(p).resolve().is_relative_to(root)

    from journal_tasks import _get_data_dir
    assert under(_get_data_dir())
    from interviews.storage import ResponseStorage
    from interviews.protocols import ProtocolManager
    from interviews.analysis import InterviewAnalyzer
    assert under(ResponseStorage().responses_dir)
    assert under(ProtocolManager().storage_dir)
    assert under(InterviewAnalyzer().storage.responses_dir)
    from music.music_client import MusicClient
    assert under(MusicClient().output_dir)
    from image_generation.comfyui_client import ComfyUIClient
    monkeypatch.delenv("IMAGE_OUTPUT_DIR", raising=False)
    assert under(ComfyUIClient().output_dir)
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(root / "elsewhere"))
    assert ComfyUIClient().output_dir == str(root / "elsewhere")  # the override still wins
