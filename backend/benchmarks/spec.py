"""
What a benchmark run is made of: scenarios, targets (models) and configurations.

Everything here is data. A scenario is a JSON file under
benchmarks/scenarios/tier2 or tier3:

    {
      "id": "recall_three_sessions",
      "tier": 2,
      "title": "...", "description": "...",
      "drivers": ["app"],                 # which drivers can run it (app, plain)
      "setup":  [ {"seed": "self_observation", ...}, ... ],
      "steps":  [ {"chat": "text", "session": "s1", "id": "intro"},
                  {"action": "write_journal", "date": "today"}, ... ],
      "probes": { "journal_today": {"probe": "journal", "date": "today"} },
      "checks": [ {"id": "...", "type": "reply_contains", "turn": "intro", "any": ["glass"]} ],
      "rubric": [ {"id": "...", "question": "...", "scale": "pass_fail",
                   "context": ["transcript", "seed", "probe:journal_today"]} ]
    }

- setup steps seed a fresh, isolated DATA_DIR before any turn (never her data).
- steps run in order: chat turns (each in a named session = its own
  conversation) and named driver actions (an allowlist, see drivers.py).
- probes are read from the driver after the steps; checks and rubric items
  can refer to them.
- checks are deterministic (checks.py); rubric items are scored by the judge
  model (judge.py).

Tier 3 configurations are defined here too: each is a set of lever values plus
which driver runs it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SCENARIO_DIR = Path(__file__).parent / "scenarios"

SEED_KINDS = {"self_observation", "opinion", "growth_edge"}
ACTIONS = {"write_journal"}
PROBES = {"sql", "journal", "active_intentions", "self_context"}
CHECK_TYPES = {"reply_contains", "reply_not_contains", "tool_called", "probe", "prompt_contains_probe"}
SCALES = {"pass_fail": (0, 1), "0-2": (0, 2)}
DRIVERS = {"app", "plain"}


class SpecError(ValueError):
    """A scenario, target or configuration is malformed."""


@dataclass
class Scenario:
    id: str
    tier: int
    title: str
    description: str
    drivers: List[str]
    setup: List[Dict[str, Any]]
    steps: List[Dict[str, Any]]
    probes: Dict[str, Dict[str, Any]]
    checks: List[Dict[str, Any]]
    rubric: List[Dict[str, Any]]
    path: Optional[str] = None

    @property
    def chat_turns(self) -> List[Dict[str, Any]]:
        return [s for s in self.steps if "chat" in s]

    @property
    def actions(self) -> List[Dict[str, Any]]:
        return [s for s in self.steps if "action" in s]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "tier": self.tier, "title": self.title, "description": self.description,
            "drivers": self.drivers, "setup": self.setup, "steps": self.steps, "probes": self.probes,
            "checks": self.checks, "rubric": self.rubric,
        }

    @classmethod
    def from_dict(cls, data: dict, path: Optional[str] = None) -> "Scenario":
        scenario = cls(
            id=data.get("id", ""),
            tier=int(data.get("tier", 0)),
            title=data.get("title", ""),
            description=data.get("description", ""),
            drivers=list(data.get("drivers") or ["app"]),
            setup=list(data.get("setup") or []),
            steps=list(data.get("steps") or []),
            probes=dict(data.get("probes") or {}),
            checks=list(data.get("checks") or []),
            rubric=list(data.get("rubric") or []),
            path=path,
        )
        validate(scenario)
        return scenario


def validate(s: Scenario) -> None:
    """Raise SpecError naming every problem in the scenario."""
    errors = []
    where = s.path or s.id or "<scenario>"
    if not s.id:
        errors.append("missing id")
    if s.tier not in (2, 3):
        errors.append(f"tier must be 2 or 3, got {s.tier}")
    if not s.title:
        errors.append("missing title")
    for d in s.drivers:
        if d not in DRIVERS:
            errors.append(f"unknown driver {d!r}")
    for i, seed in enumerate(s.setup):
        if seed.get("seed") not in SEED_KINDS:
            errors.append(f"setup[{i}]: seed must be one of {sorted(SEED_KINDS)}")
    turn_ids = set()
    if not s.chat_turns:
        errors.append("needs at least one chat step")
    for i, step in enumerate(s.steps):
        if "chat" in step:
            if not step.get("session"):
                errors.append(f"steps[{i}]: chat step needs a session")
            if step.get("id"):
                if step["id"] in turn_ids:
                    errors.append(f"steps[{i}]: duplicate turn id {step['id']!r}")
                turn_ids.add(step["id"])
        elif "action" in step:
            if step["action"] not in ACTIONS:
                errors.append(f"steps[{i}]: unknown action {step['action']!r}")
        else:
            errors.append(f"steps[{i}]: needs 'chat' or 'action'")
    for name, probe in s.probes.items():
        if probe.get("probe") not in PROBES:
            errors.append(f"probes.{name}: probe must be one of {sorted(PROBES)}")
    ids = set()
    for i, check in enumerate(s.checks):
        cid = check.get("id")
        if not cid or cid in ids:
            errors.append(f"checks[{i}]: missing or duplicate id")
        ids.add(cid)
        ctype = check.get("type")
        if ctype not in CHECK_TYPES:
            errors.append(f"checks[{i}]: unknown type {ctype!r}")
        if ctype in ("reply_contains", "reply_not_contains", "tool_called", "prompt_contains_probe") \
                and check.get("turn") not in turn_ids:
            errors.append(f"checks[{i}]: turn {check.get('turn')!r} is not a chat step id")
        if ctype in ("probe", "prompt_contains_probe") and check.get("probe") not in s.probes:
            errors.append(f"checks[{i}]: probe {check.get('probe')!r} is not defined")
    for i, item in enumerate(s.rubric):
        rid = item.get("id")
        if not rid or rid in ids:
            errors.append(f"rubric[{i}]: missing or duplicate id")
        ids.add(rid)
        if not item.get("question"):
            errors.append(f"rubric[{i}]: missing question")
        if item.get("scale", "pass_fail") not in SCALES:
            errors.append(f"rubric[{i}]: scale must be one of {sorted(SCALES)}")
        for ctx in item.get("context") or ["transcript"]:
            if ctx in ("transcript", "seed"):
                continue
            if ctx.startswith("probe:") and ctx[6:] in s.probes:
                continue
            if ctx.startswith("turns:") and set(ctx[6:].split(",")) <= turn_ids:
                continue
            errors.append(f"rubric[{i}]: unknown context {ctx!r}")
    if errors:
        raise SpecError(f"{where}: " + "; ".join(errors))


def load_scenarios(tier: int, ids: Optional[List[str]] = None,
                   directory: Optional[Path] = None) -> List[Scenario]:
    """Load (and validate) every scenario for a tier, optionally filtered by id."""
    base = (directory or SCENARIO_DIR) / f"tier{tier}"
    scenarios = []
    for path in sorted(base.glob("*.json")):
        with open(path) as f:
            scenario = Scenario.from_dict(json.load(f), path=str(path))
        if scenario.tier != tier:
            raise SpecError(f"{path}: tier {scenario.tier} file in tier{tier}/")
        scenarios.append(scenario)
    if ids:
        known = {s.id for s in scenarios}
        missing = [i for i in ids if i not in known]
        if missing:
            raise SpecError(f"unknown tier {tier} scenario(s): {', '.join(missing)}")
        scenarios = [s for s in scenarios if s.id in ids]
    return scenarios


# ---------------------------------------------------------------------------
# Targets (which model) and configurations (which levers / driver)
# ---------------------------------------------------------------------------

PROVIDERS = {"anthropic", "openai", "ollama"}


@dataclass(frozen=True)
class Target:
    """A model under test: provider plus model id ("ollama:qwen3:14b")."""
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    @classmethod
    def parse(cls, text: str) -> "Target":
        provider, sep, model = text.partition(":")
        if not sep or provider not in PROVIDERS or not model:
            raise SpecError(f"target {text!r}: expected provider:model with provider in {sorted(PROVIDERS)}")
        return cls(provider, model)


@dataclass(frozen=True)
class Config:
    """A Tier 3 configuration: lever values plus the driver that runs it.

    Every app configuration starts from CASS_PROFILE=test (every lever off,
    core chat still runs) so nothing autonomous spends tokens during a run;
    `levers` then turns on what the configuration is about.
    """
    name: str
    driver: str
    levers: Dict[str, bool] = field(default_factory=dict)
    description: str = ""
    meaningful: bool = True
    caveat: str = ""


# The same base for Tier 2 cells: the conversation path with every prompt
# section on, nothing autonomous running.
TIER2_LEVERS = {"self_context": True}

TIER3_CONFIGS: Dict[str, Config] = {
    "full": Config(
        "full", "app", {"self_context": True},
        "Full Cass conversation path: memory retrieval, self-model, continuous context, "
        "self-context section on. Background subsystems are off (they don't run during a "
        "scripted conversation and would spend on their own)."),
    "self_context_off": Config(
        "self_context_off", "app", {"self_context": False},
        "As full, with the self_context lever off.",
        meaningful=False,
        caveat="Placeholder until the self-context design (#63) exists. Today this lever "
               "toggles an early version of the section, so a difference here does not "
               "measure the designed self-context and must not be reported as if it did."),
    "plain_kernel": Config(
        "plain_kernel", "plain", {},
        "The same model with only the Temple-Codex kernel as its system prompt: no "
        "memory, no self-model, no tools, no app. History is kept within a session only."),
}


def parse_configs(names: Optional[List[str]]) -> List[Config]:
    if not names:
        return list(TIER3_CONFIGS.values())
    unknown = [n for n in names if n not in TIER3_CONFIGS]
    if unknown:
        raise SpecError(f"unknown configuration(s): {', '.join(unknown)} "
                        f"(known: {', '.join(TIER3_CONFIGS)})")
    return [TIER3_CONFIGS[n] for n in names]


def tier2_config() -> Config:
    return Config("cass", "app", dict(TIER2_LEVERS), "Cass conversation path (Tier 2 base).")
