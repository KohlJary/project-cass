"""
Issue #49: the LoRA benchmark counted only bare metacognitive tags
(<observe>), so tags with attributes (<observe target="self">) read 0.
"""
import importlib.util
import sys
import types
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "training" / "benchmark_cass_lora.py"


def _load_benchmark(monkeypatch):
    # The script imports torch and unsloth at module load; the tag counter
    # needs neither, so stand in empty modules for them.
    unsloth = types.ModuleType("unsloth")
    unsloth.FastLanguageModel = object
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    monkeypatch.setitem(sys.modules, "unsloth", unsloth)
    spec = importlib.util.spec_from_file_location("benchmark_cass_lora", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_counts_tags_with_attributes(monkeypatch):
    bench = _load_benchmark(monkeypatch)
    counts = bench.count_metacognitive_tags('<observe target="self">x</observe>')
    assert counts["observe"] == 1
    assert counts["total"] == 1


def test_counts_bare_tags_and_ignores_lookalikes(monkeypatch):
    bench = _load_benchmark(monkeypatch)
    text = (
        "<hold>a</hold> <note type='x'>b</note> <FEEL>c</FEEL> "
        "<gesture:wave> <observer>not a tag</observer> <notes>no</notes>"
    )
    counts = bench.count_metacognitive_tags(text)
    assert counts == {
        "observe": 0, "hold": 1, "note": 1, "feel": 1, "gesture": 1, "total": 4,
    }
