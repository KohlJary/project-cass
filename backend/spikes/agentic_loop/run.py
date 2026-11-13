"""
Run one arm of the agentic-loop spike.

  cd backend && source venv/bin/activate
  python -m spikes.agentic_loop.run --arm sdk  --model claude-sonnet-4-6
  python -m spikes.agentic_loop.run --arm loop --provider anthropic --model claude-sonnet-4-6
  python -m spikes.agentic_loop.run --arm loop --provider ollama    --model qwen3:14b
  python -m spikes.agentic_loop.run --arm sdk  --model qwen3-14b --proxy http://localhost:4000

Writes <out>/<arm>-<model>-<time>/: summary.json, transcript.json, workspace/.
"""
import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from .common import seed_workspace, snapshot  # noqa: E402  (sets a scratch DATA_DIR first)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["sdk", "loop"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--provider", choices=["anthropic", "openai", "ollama"], default="anthropic")
    ap.add_argument("--proxy", help="Anthropic-compatible proxy URL for the SDK arm (LiteLLM)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--budget-usd", type=float, default=3.0)
    a = ap.parse_args()

    tag = f"{a.arm}-{a.provider if a.arm == 'loop' else ('proxy' if a.proxy else 'anthropic')}-{a.model.replace(':', '_').replace('/', '_')}-{time.strftime('%H%M%S')}"
    run_dir = Path(a.out) / tag
    ws = seed_workspace(run_dir)
    before = snapshot(ws)
    if a.arm == "sdk":
        from .sdk_arm import run
        rec = run(ws, a.model, base_url=a.proxy, max_turns=a.max_steps, budget_usd=a.budget_usd)
    else:
        from .own_loop import run
        rec = run(ws, a.provider, a.model, max_steps=a.max_steps)
    summary = rec.save(run_dir, ws, before)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("said",)}, indent=2))
    print("said:", json.dumps(summary["said"], indent=2)[:1500])
    print("run dir:", run_dir)


if __name__ == "__main__":
    main()
