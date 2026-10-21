"""
Issues #22 and #92: several stores defaulted to CWD-relative 'data/...' paths, so
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

from config import DATA_DIR
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

# Issue #92: the remaining CWD-relative defaults.
from roadmap import RoadmapManager
RoadmapManager(daemon_id="anchor-test")._save_milestones([])

from self_model import SelfManager
SelfManager().differentiation_file

from self_model_graph import SelfModelGraph
SelfModelGraph().save()

from refactor_scout.database import ScoutDatabase
from refactor_scout.config import load_config
ScoutDatabase()
load_config()

from llm_bench.chat_reasoning import ChatReasoningBenchmark
from llm_bench.models import default_results_dir
ChatReasoningBenchmark()
assert default_results_dir().is_relative_to(DATA_DIR)

from art_study.wikiart import _artwork_image_dir
assert _artwork_image_dir() == DATA_DIR / "art_study" / "images"

# The Wonderland server's startup hook, without its WONDERLAND_DATA_DIR override.
import asyncio
from wonderland import server
asyncio.run(server.startup())
print("ok")
"""


def test_default_paths_write_under_data_dir(tmp_path):
    cwd = tmp_path / "cwd"
    data_dir = tmp_path / "data"
    cwd.mkdir()
    env = dict(os.environ, DATA_DIR=str(data_dir), CASS_STRICT="0")
    env.pop("PYTHONPATH", None)
    env.pop("WONDERLAND_DATA_DIR", None)
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
                     "wonderland/sessions", "roadmap/milestones.json", "cass",
                     "cass/self_model_graph.json", "scout", "llm_bench/results"):
        assert expected in written, (expected, sorted(written)[:40])
