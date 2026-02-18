"""
CLI interface for LLM benchmarking.

Usage:
    python -m llm_bench status              # Show capture status and available models
    python -m llm_bench pull                # Pull recommended models
    python -m llm_bench capture             # Enable capture mode
    python -m llm_bench run <call_site>     # Run benchmark
    python -m llm_bench report <call_site>  # Generate report from results
"""

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .models import (
    ALL_MODELS,
    RECOMMENDED_MODELS,
    Provider,
    check_ollama_models,
    get_models_to_pull,
)
from .capture import CaptureStore, enable_capture
from .runner import BenchmarkRunner, run_benchmark
from .report import generate_comparison_report, generate_migration_matrix


def cmd_status(args):
    """Show status of captures and models."""
    print("=" * 60)
    print("LLM Benchmark Status")
    print("=" * 60)

    # Capture status
    store = CaptureStore()
    sites = store.list_call_sites()

    print("\n## Captured Data")
    if sites:
        total = 0
        for site in sites:
            count = store.count(site)
            total += count
            print(f"  {site}: {count} captures")
        print(f"  TOTAL: {total} captures")
    else:
        print("  No captures yet. Enable capture mode with: python -m llm_bench capture")

    # Model status
    print("\n## Available Models")

    ollama_status = check_ollama_models()

    for name, config in ALL_MODELS.items():
        status = ""
        if config.provider == Provider.OLLAMA:
            installed = ollama_status.get(name, False)
            status = "✅ installed" if installed else "❌ not installed"
        elif config.provider == Provider.ANTHROPIC:
            status = "☁️ API"
        elif config.provider == Provider.OPENAI:
            status = "☁️ API"

        recommended = "⭐" if name in RECOMMENDED_MODELS else " "
        print(f"  {recommended} {name:20} {status:20} ({config.notes[:40]}...)")

    print("\n## Recommended Models for Testing")
    print(f"  {', '.join(RECOMMENDED_MODELS)}")

    # Models to pull
    to_pull = [m for m in get_models_to_pull() if not ollama_status.get(m.name, False)]
    if to_pull:
        print(f"\n## Models to Pull ({len(to_pull)})")
        for model in to_pull[:5]:
            print(f"  {model.pull_command}")
        if len(to_pull) > 5:
            print(f"  ... and {len(to_pull) - 5} more")


def cmd_pull(args):
    """Pull recommended Ollama models."""
    ollama_status = check_ollama_models()
    to_pull = get_models_to_pull()

    if args.model:
        # Pull specific model
        to_pull = [m for m in to_pull if m.name == args.model or args.model in m.model_id]

    if not to_pull:
        print("All recommended models are already installed!")
        return

    print(f"Pulling {len(to_pull)} models...")

    for model in to_pull:
        if ollama_status.get(model.name, False) and not args.force:
            print(f"  Skipping {model.name} (already installed)")
            continue

        print(f"\n  Pulling {model.name}...")
        print(f"  $ {model.pull_command}")

        if not args.dry_run:
            result = subprocess.run(
                model.pull_command.split(), capture_output=False
            )
            if result.returncode != 0:
                print(f"  ❌ Failed to pull {model.name}")
            else:
                print(f"  ✅ {model.name} installed")


def cmd_capture(args):
    """Enable or show capture status."""
    if args.enable:
        print("To enable capture mode, set environment variable:")
        print("  export LLM_BENCH_CAPTURE=true")
        print("")
        print("Then restart the backend. Captures will be saved to:")
        print(f"  {CaptureStore().base_dir}")
    else:
        import os
        enabled = os.environ.get("LLM_BENCH_CAPTURE", "false").lower() == "true"
        print(f"Capture mode: {'ENABLED' if enabled else 'DISABLED'}")
        print(f"Capture directory: {CaptureStore().base_dir}")


def cmd_run(args):
    """Run benchmark for a call site."""
    call_site = args.call_site

    # Parse models
    if args.models:
        models = args.models.split(",")
    else:
        models = RECOMMENDED_MODELS

    # Check for captures
    store = CaptureStore()
    count = store.count(call_site)

    if count == 0:
        print(f"No captures found for call site: {call_site}")
        print(f"Available call sites: {store.list_call_sites()}")
        return

    print(f"Running benchmark: {call_site}")
    print(f"  Captures: {min(count, args.limit)}")
    print(f"  Models: {', '.join(models)}")
    print("")

    # Run benchmark
    output_dir = Path(args.output) if args.output else Path("data/llm_bench/results")

    async def _run():
        return await run_benchmark(
            call_site=call_site,
            models=models,
            limit=args.limit,
            output_dir=output_dir,
        )

    results = asyncio.run(_run())

    # Generate report
    report_path = output_dir / f"{call_site}_report.md"
    report = generate_comparison_report(call_site, results, report_path)

    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
    print(f"\nReport saved to: {report_path}")


def cmd_report(args):
    """Generate report from existing results."""
    results_dir = Path(args.results_dir)

    if args.call_site:
        # Single call site report
        results_files = list(results_dir.glob(f"{args.call_site}_*.json"))
        if not results_files:
            print(f"No results found for {args.call_site}")
            return

        # Load most recent
        results_file = sorted(results_files)[-1]
        with open(results_file) as f:
            data = json.load(f)

        from .runner import BenchmarkResult
        from .capture import CapturedInput

        results = []
        for item in data:
            capture = CapturedInput.from_dict(item["capture"])
            result = BenchmarkResult(capture=capture)
            # Reconstruct outputs
            from .runner import ModelOutput
            for out_data in item["outputs"]:
                result.outputs.append(ModelOutput(**out_data))
            results.append(result)

        report = generate_comparison_report(
            args.call_site,
            results,
            results_dir / f"{args.call_site}_report.md",
        )
        print(report)

    else:
        # Migration matrix across all call sites
        print("Generating migration matrix...")

        all_results = {}
        for results_file in results_dir.glob("*_2*.json"):  # Match timestamp pattern
            call_site = results_file.stem.rsplit("_", 2)[0]

            with open(results_file) as f:
                data = json.load(f)

            from .runner import BenchmarkResult, ModelOutput
            from .capture import CapturedInput

            results = []
            for item in data:
                capture = CapturedInput.from_dict(item["capture"])
                result = BenchmarkResult(capture=capture)
                for out_data in item["outputs"]:
                    result.outputs.append(ModelOutput(**out_data))
                results.append(result)

            if call_site not in all_results:
                all_results[call_site] = []
            all_results[call_site].extend(results)

        if not all_results:
            print("No results found. Run benchmarks first.")
            return

        report = generate_migration_matrix(
            all_results,
            results_dir / "migration_matrix.md",
        )
        print(report)


def cmd_synthetic(args):
    """Generate synthetic test data for a call site."""
    from .capture import CapturedInput, CaptureStore

    store = CaptureStore()

    # Synthetic data generators for different call sites
    generators = {
        "title_generation": _generate_title_captures,
        "grimoire.ask_yes_no": _generate_yes_no_captures,
        "grimoire.rate": _generate_rate_captures,
    }

    if args.call_site not in generators:
        print(f"No synthetic generator for: {args.call_site}")
        print(f"Available: {list(generators.keys())}")
        return

    captures = generators[args.call_site](args.count)

    for capture in captures:
        store.save(capture)

    print(f"Generated {len(captures)} synthetic captures for {args.call_site}")


def _generate_title_captures(count: int) -> list:
    """Generate synthetic title generation captures."""
    from .capture import CapturedInput

    conversations = [
        ("Hi, I'm interested in learning Python programming.", "Great! Python is a wonderful language to start with. What aspects interest you most?"),
        ("Can you help me debug this React component?", "Of course! Please share the component code and describe the issue you're seeing."),
        ("I need to set up a CI/CD pipeline for my project.", "I'd be happy to help with that. What platform are you using - GitHub Actions, GitLab CI, or something else?"),
        ("What's the best way to handle authentication in a web app?", "There are several approaches depending on your needs. Are you building a SPA, traditional web app, or API?"),
        ("I'm having trouble with my Docker containers.", "Let's troubleshoot that. Can you describe what's happening when you try to run the containers?"),
        ("How do I optimize my PostgreSQL queries?", "Query optimization is crucial for performance. Can you share the slow query and the table structure?"),
        ("I want to learn about machine learning.", "Machine learning is a fascinating field! Do you have a specific area in mind, like computer vision or NLP?"),
        ("My Kubernetes pods keep crashing.", "That's frustrating. Let's look at the pod logs and events to understand what's happening."),
        ("Can you explain async/await in JavaScript?", "Absolutely! Async/await makes asynchronous code much more readable. Let me walk you through it."),
        ("I need help designing a database schema.", "Database design is important to get right. What kind of data will you be storing and what are your access patterns?"),
    ]

    captures = []
    for i in range(count):
        user_msg, assistant_msg = conversations[i % len(conversations)]
        captures.append(CapturedInput(
            call_site="title_generation",
            timestamp=datetime.now().isoformat(),
            system_prompt="Generate a concise 3-6 word title for this conversation.",
            user_prompt=f"User: {user_msg}\n\nAssistant: {assistant_msg}",
            expected_format="text",
            max_tokens=50,
            temperature=0.7,
        ))

    return captures


def _generate_yes_no_captures(count: int) -> list:
    """Generate synthetic yes/no classification captures."""
    from .capture import CapturedInput

    questions = [
        ("Is the user asking about programming?", {"message": "Can you help me write a function?"}),
        ("Does this require a code review?", {"message": "Here's my implementation, what do you think?"}),
        ("Is the user frustrated?", {"message": "This still doesn't work, I've tried everything!"}),
        ("Should we suggest documentation?", {"message": "I'm not sure how this API works."}),
        ("Is this a security concern?", {"message": "I want to store passwords in my database."}),
        ("Does the user need clarification?", {"message": "Just do the thing."}),
        ("Is this related to debugging?", {"message": "Why am I getting this error?"}),
        ("Should we offer alternatives?", {"message": "I'm using jQuery for this."}),
    ]

    captures = []
    for i in range(count):
        question, context = questions[i % len(questions)]
        captures.append(CapturedInput(
            call_site="grimoire.ask_yes_no",
            timestamp=datetime.now().isoformat(),
            system_prompt="Answer the question with a JSON object containing 'answer' (boolean) and 'reasoning' (string).",
            user_prompt=question,
            context=context,
            expected_format="json",
            json_schema={
                "required": ["answer"],
                "properties": {
                    "answer": {"type": "boolean"},
                    "reasoning": {"type": "string"},
                },
            },
            max_tokens=200,
            temperature=0.3,
        ))

    return captures


def _generate_rate_captures(count: int) -> list:
    """Generate synthetic rating captures."""
    from .capture import CapturedInput

    prompts = [
        ("Rate the urgency of this request from 0.0 to 1.0", {"message": "I need this by tomorrow!"}),
        ("Rate the technical complexity", {"code": "def add(a, b): return a + b"}),
        ("Rate the user's expertise level", {"message": "I've been coding for 10 years but new to Rust"}),
        ("Rate how helpful the response would be", {"response": "Have you tried turning it off and on again?"}),
        ("Rate the code quality", {"code": "for i in range(len(lst)): print(lst[i])"}),
    ]

    captures = []
    for i in range(count):
        prompt, context = prompts[i % len(prompts)]
        captures.append(CapturedInput(
            call_site="grimoire.rate",
            timestamp=datetime.now().isoformat(),
            system_prompt="Provide a rating from 0.0 to 1.0 as JSON with 'rating' (float) and 'reasoning' (string).",
            user_prompt=prompt,
            context=context,
            expected_format="json",
            json_schema={
                "required": ["rating"],
                "properties": {
                    "rating": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
            },
            max_tokens=200,
            temperature=0.3,
        ))

    return captures


def main():
    parser = argparse.ArgumentParser(
        description="LLM Benchmarking Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m llm_bench status
    python -m llm_bench pull
    python -m llm_bench pull --model mistral:7b
    python -m llm_bench synthetic title_generation --count 20
    python -m llm_bench run title_generation --models haiku,llama3.1:8b,qwen2.5:14b
    python -m llm_bench report --results-dir data/llm_bench/results
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status
    status_parser = subparsers.add_parser("status", help="Show capture and model status")

    # pull
    pull_parser = subparsers.add_parser("pull", help="Pull Ollama models")
    pull_parser.add_argument("--model", help="Specific model to pull")
    pull_parser.add_argument("--force", action="store_true", help="Re-pull even if installed")
    pull_parser.add_argument("--dry-run", action="store_true", help="Show commands without running")

    # capture
    capture_parser = subparsers.add_parser("capture", help="Capture mode status")
    capture_parser.add_argument("--enable", action="store_true", help="Show how to enable")

    # run
    run_parser = subparsers.add_parser("run", help="Run benchmark")
    run_parser.add_argument("call_site", help="Call site to benchmark")
    run_parser.add_argument("--models", help="Comma-separated list of models")
    run_parser.add_argument("--limit", type=int, default=10, help="Max captures to test")
    run_parser.add_argument("--output", help="Output directory")

    # report
    report_parser = subparsers.add_parser("report", help="Generate report")
    report_parser.add_argument("--call-site", help="Specific call site (or all for matrix)")
    report_parser.add_argument(
        "--results-dir",
        default="data/llm_bench/results",
        help="Results directory",
    )

    # synthetic
    synthetic_parser = subparsers.add_parser("synthetic", help="Generate synthetic test data")
    synthetic_parser.add_argument("call_site", help="Call site to generate data for")
    synthetic_parser.add_argument("--count", type=int, default=10, help="Number of captures")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "pull":
        cmd_pull(args)
    elif args.command == "capture":
        cmd_capture(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "synthetic":
        cmd_synthetic(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
