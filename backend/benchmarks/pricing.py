"""
Cost estimates and the budget cap.

Before a run, `estimate_cell` turns a planned cell (scenario x target x
configuration) into a token and dollar estimate from fixed per-step
allowances; the CLI refuses to start when the total is over the cap. During a
run, `Meter` counts what was actually spent (from the token ledger of the
cell's own isolated database, and from the judge's replies) and stops before
a step whose allowance would cross the cap. A run can therefore end early
with status "budget_stop"; it cannot knowingly start a step it can't afford.

The per-step allowances are guesses, set high on purpose, until the first
real run's ledger can calibrate them. The prices are copied from
llm_bench/models.py and were not re-checked against the providers' price
lists; check them before relying on an estimate.
A model with no known price is refused (pass --price to supply one), except
Ollama, which is local and costs $0 here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple

PRICES_SOURCE = "llm_bench/models.py (not re-checked against provider price lists)"

# USD per million tokens: (input, output).
PRICES: Dict[str, Tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}

# Token allowances per step: (input, output). Deliberately generous.
ALLOWANCE = {
    # One websocket chat turn on the app: the continuous-context system prompt
    # plus tool definitions, a tool continuation now and then, and the
    # background calls a turn sets off (title, summaries).
    "app_turn": (60_000, 1_500),
    # One plain kernel turn: the kernel plus the session's history.
    "plain_turn": (8_000, 800),
    # A named action (journal generation reads the day's conversations).
    "action": (20_000, 2_000),
    # One rubric item scored by the judge (transcript + context + question).
    "judge_item": (12_000, 500),
}


class UnknownPrice(ValueError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def price_for(provider: str, model: str, extra: Optional[Dict[str, Tuple[float, float]]] = None
              ) -> Tuple[float, float]:
    if provider == "ollama":
        return (0.0, 0.0)
    table = dict(PRICES)
    table.update(extra or {})
    if model in table:
        return table[model]
    raise UnknownPrice(f"no price for {provider}:{model}; pass --price {model}=IN/OUT (USD per Mtok)")


def cost(provider: str, model: str, input_tokens: int, output_tokens: int,
         extra: Optional[Dict[str, Tuple[float, float]]] = None, *, conservative: bool = False) -> float:
    """Dollar cost of a usage. conservative=True prices an unknown model at the
    highest known price instead of raising (used for spend actually measured)."""
    try:
        p_in, p_out = price_for(provider, model, extra)
    except UnknownPrice:
        if not conservative:
            raise
        table = dict(PRICES)
        table.update(extra or {})
        p_in = max(v[0] for v in table.values())
        p_out = max(v[1] for v in table.values())
    return input_tokens / 1e6 * p_in + output_tokens / 1e6 * p_out


@dataclass
class Estimate:
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    calls: int = 0
    breakdown: Dict[str, float] = field(default_factory=dict)

    def add(self, label: str, provider: str, model: str, allowance: Tuple[int, int], n: int = 1,
            extra=None) -> None:
        i, o = allowance[0] * n, allowance[1] * n
        usd = cost(provider, model, i, o, extra)
        self.input_tokens += i
        self.output_tokens += o
        self.usd += usd
        self.calls += n
        self.breakdown[label] = self.breakdown.get(label, 0.0) + usd

    def to_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "usd": round(self.usd, 4), "calls": self.calls,
                "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()}}


def step_allowance(driver: str, step: dict) -> Tuple[int, int]:
    if "chat" in step:
        return ALLOWANCE["app_turn"] if driver == "app" else ALLOWANCE["plain_turn"]
    return ALLOWANCE["action"]


def estimate_cell(scenario, target, config, judge, extra=None) -> Estimate:
    """Estimate one cell. `judge` is a Target (or None when rubric items are skipped)."""
    est = Estimate()
    for step in scenario.steps:
        if config.driver == "plain" and "action" in step:
            continue  # the plain driver has no app actions
        kind = "turns" if "chat" in step else "actions"
        est.add(kind, target.provider, target.model, step_allowance(config.driver, step), extra=extra)
    if judge is not None and scenario.rubric:
        est.add("judge", judge.provider, judge.model, ALLOWANCE["judge_item"], n=len(scenario.rubric),
                extra=extra)
    return est


class Meter:
    """Running spend against a cap, in dollars."""

    def __init__(self, cap_usd: float, spent_usd: float = 0.0):
        self.cap_usd = float(cap_usd)
        self.spent_usd = float(spent_usd)

    @property
    def remaining(self) -> float:
        return self.cap_usd - self.spent_usd

    def can_afford(self, usd: float) -> bool:
        return self.spent_usd + usd <= self.cap_usd + 1e-12

    def require(self, usd: float, what: str) -> None:
        if not self.can_afford(usd):
            raise BudgetExceeded(
                f"{what}: allowance ${usd:.4f} would exceed the cap "
                f"(spent ${self.spent_usd:.4f} of ${self.cap_usd:.2f})")

    def charge(self, usd: float) -> None:
        self.spent_usd += usd


def ledger_cost(rows: Iterable[Tuple[str, str, int, int]], extra=None) -> float:
    """Cost of token-ledger rows (provider, model, input_tokens, output_tokens)."""
    return sum(cost(p or "anthropic", m or "", i or 0, o or 0, extra, conservative=True)
               for p, m, i, o in rows)
