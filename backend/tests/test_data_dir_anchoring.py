"""
Issue #22: several stores defaulted to CWD-relative 'data/...' paths, so
what they wrote depended on where the process started instead of DATA_DIR.
Each one is constructed here with defaults, in a fresh interpreter whose
CWD is an empty directory and whose DATA_DIR is a temp directory; every
write must land under DATA_DIR and the CWD must stay empty.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

# The wonderland package imports anthropic at load; the fast CI job doesn't
# install it, the full job runs this.
pytest.importorskip("anthropic")

BACKEND = Path(__file__).resolve().parent.parent

_SCRIPT = """
import sys
sys.path.insert(0, sys.argv[1])

from database.migrations import init_database
init_database()  # under DATA_DIR; SessionController's planner needs the schema

from wonderland.world import WonderlandWorld
from wonderland.world_clock import WorldClock
from wonderland.npc_state import NPCStateManager
from home_intelligence import HomeIntelligence
from sources.world_state_source import WorldStateSource
from scheduling.contradiction_scheduler import ContradictionDetectionTask

WonderlandWorld()
WorldClock()
NPCStateManager()
HomeIntelligence()
WorldStateSource(daemon_id="anchor-test")
ContradictionDetectionTask(daemon_id="anchor-test")

from world.article_consumer import ArticleConsumer
from wonderland.session_controller import SessionController

ArticleConsumer("anchor-test")
SessionController()
print("ok")
"""


def test_default_paths_write_under_data_dir(tmp_path):
    cwd = tmp_path / "cwd"
    data_dir = tmp_path / "data"
    cwd.mkdir()
    env = dict(os.environ, DATA_DIR=str(data_dir), CASS_STRICT="0")
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(BACKEND)],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "ok" in result.stdout

    assert list(cwd.iterdir()) == [], "something wrote relative to the CWD"
    written = {p.relative_to(data_dir).as_posix() for p in data_dir.rglob("*")}
    for expected in ("wonderland", "wonderland/npc_state", "home_intelligence",
                     "world_state", "anchor-test", "articles/cache",
                     "wonderland/sessions"):
        assert expected in written, (expected, sorted(written)[:40])
