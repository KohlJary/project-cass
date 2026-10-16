"""
No call site may name a model the API has retired: such calls 404 and the
failure is swallowed (her nightly dream failed this way 2026-10-14/15).
"""
import pathlib
import re

import pytest

from llm_config import RETIRED_MODELS, ModelAssignment, current_model_id

BACKEND = pathlib.Path(__file__).resolve().parent.parent
# Places allowed to name retired IDs: the map itself, historic pricing, and
# benchmark/one-off scripts that record what was run.
ALLOWED = {"llm_config.py", "token_tracker.py"}
ALLOWED_DIRS = {"tests", "venv", "llm_bench", "scripts", "dreaming/test_logs"}


def _code_files():
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel in ALLOWED or any(rel.startswith(d + "/") for d in ALLOWED_DIRS):
            continue
        if rel.endswith("test_dream.py"):
            continue
        yield rel, path.read_text(errors="ignore")


@pytest.mark.unit
def test_no_code_names_a_retired_model():
    pattern = re.compile("|".join(re.escape(m) for m in RETIRED_MODELS))
    offenders = [rel for rel, text in _code_files()
                 if any(not line.lstrip().startswith("#") and pattern.search(line)
                        for line in text.splitlines())]
    assert offenders == []


@pytest.mark.unit
def test_saved_assignments_map_retired_models_on_read():
    a = ModelAssignment.from_dict({"provider": "anthropic", "model_id": "claude-sonnet-4-20250514",
                                   "fallback_model_id": "claude-3-5-haiku-20241022"})
    assert a.model_id == "claude-sonnet-4-6"
    assert a.fallback_model_id == "claude-haiku-4-5-20251001"
    assert current_model_id("qwen2.5:latest") == "qwen2.5:latest"
