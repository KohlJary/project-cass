"""
Report generation for benchmark results.

Generates comparison reports across models and call sites.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .runner import BenchmarkResult, ModelOutput
from .scorers import score_output, get_scorer, ScoreResult


@dataclass
class ModelSummary:
    """Summary statistics for a model across multiple captures."""

    model_name: str
    model_id: str
    provider: str

    # Counts
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0

    # Score averages
    avg_format_compliance: float = 0.0
    avg_completeness: float = 0.0
    avg_coherence: float = 0.0
    avg_overall: float = 0.0

    # Performance
    avg_latency_ms: float = 0.0
    avg_tokens_per_second: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # JSON-specific
    json_valid_rate: float = 0.0
    json_schema_valid_rate: float = 0.0


def summarize_model_results(
    model_name: str, results: list[tuple[BenchmarkResult, ModelOutput, ScoreResult]]
) -> ModelSummary:
    """Summarize results for a single model."""
    if not results:
        return ModelSummary(model_name=model_name, model_id="", provider="")

    first_output = results[0][1]
    summary = ModelSummary(
        model_name=model_name,
        model_id=first_output.model_id,
        provider=first_output.provider,
        total_runs=len(results),
    )

    format_scores = []
    completeness_scores = []
    coherence_scores = []
    overall_scores = []
    latencies = []
    tps_values = []
    json_valid_count = 0
    json_schema_valid_count = 0
    json_total = 0

    for _, output, score in results:
        if output.error:
            summary.failed_runs += 1
        else:
            summary.successful_runs += 1

        format_scores.append(score.format_compliance)
        completeness_scores.append(score.completeness)
        coherence_scores.append(score.coherence)
        overall_scores.append(score.overall)

        if output.latency_ms > 0:
            latencies.append(output.latency_ms)

        if score.tokens_per_second > 0:
            tps_values.append(score.tokens_per_second)

        summary.total_input_tokens += output.input_tokens
        summary.total_output_tokens += output.output_tokens

        if score.json_valid is not None:
            json_total += 1
            if score.json_valid:
                json_valid_count += 1
            if score.json_schema_valid:
                json_schema_valid_count += 1

    # Calculate averages
    if format_scores:
        summary.avg_format_compliance = sum(format_scores) / len(format_scores)
        summary.avg_completeness = sum(completeness_scores) / len(completeness_scores)
        summary.avg_coherence = sum(coherence_scores) / len(coherence_scores)
        summary.avg_overall = sum(overall_scores) / len(overall_scores)

    if latencies:
        summary.avg_latency_ms = sum(latencies) / len(latencies)

    if tps_values:
        summary.avg_tokens_per_second = sum(tps_values) / len(tps_values)

    if json_total > 0:
        summary.json_valid_rate = json_valid_count / json_total
        summary.json_schema_valid_rate = json_schema_valid_count / json_total

    return summary


def generate_comparison_report(
    call_site: str,
    results: list[BenchmarkResult],
    output_path: Optional[Path] = None,
) -> str:
    """
    Generate a comparison report for a call site benchmark.

    Returns markdown report text.
    """
    if not results:
        return f"# Benchmark Report: {call_site}\n\nNo results to report."

    # Get the scorer for this call site
    scorer = get_scorer(call_site)

    # Group results by model
    model_results: dict[str, list[tuple[BenchmarkResult, ModelOutput, ScoreResult]]] = {}

    for result in results:
        for output in result.outputs:
            if output.model_name not in model_results:
                model_results[output.model_name] = []

            score = scorer(output, result.capture)
            model_results[output.model_name].append((result, output, score))

    # Generate summaries
    summaries = {
        name: summarize_model_results(name, data)
        for name, data in model_results.items()
    }

    # Sort by overall score
    sorted_models = sorted(
        summaries.items(), key=lambda x: x[1].avg_overall, reverse=True
    )

    # Build report
    lines = [
        f"# LLM Benchmark Report: {call_site}",
        f"",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total captures tested: {len(results)}",
        f"Models compared: {len(summaries)}",
        f"",
        f"## Summary Rankings",
        f"",
        f"| Rank | Model | Overall | Format | Complete | Coherent | Latency | TPS |",
        f"|------|-------|---------|--------|----------|----------|---------|-----|",
    ]

    for rank, (name, summary) in enumerate(sorted_models, 1):
        lines.append(
            f"| {rank} | {name} | "
            f"{summary.avg_overall:.2f} | "
            f"{summary.avg_format_compliance:.2f} | "
            f"{summary.avg_completeness:.2f} | "
            f"{summary.avg_coherence:.2f} | "
            f"{summary.avg_latency_ms:.0f}ms | "
            f"{summary.avg_tokens_per_second:.0f} |"
        )

    lines.extend([
        f"",
        f"## Recommendation",
        f"",
    ])

    if sorted_models:
        best_model = sorted_models[0][1]
        best_name = sorted_models[0][0]

        # Find best local model
        local_models = [(n, s) for n, s in sorted_models if s.provider == "ollama"]
        best_local = local_models[0] if local_models else None

        lines.append(f"**Best overall:** {best_name} (score: {best_model.avg_overall:.2f})")

        if best_local and best_local[0] != best_name:
            lines.append(
                f"**Best local model:** {best_local[0]} "
                f"(score: {best_local[1].avg_overall:.2f})"
            )

        # Migration recommendation
        lines.extend([
            f"",
            f"### Migration Analysis",
            f"",
        ])

        haiku_summary = summaries.get("Haiku 4.5")
        if haiku_summary and best_local:
            score_diff = best_local[1].avg_overall - haiku_summary.avg_overall
            latency_ratio = (
                haiku_summary.avg_latency_ms / best_local[1].avg_latency_ms
                if best_local[1].avg_latency_ms > 0
                else 0
            )

            if score_diff >= -0.1 and best_local[1].avg_overall >= 0.7:
                lines.append(
                    f"✅ **MIGRATE**: {best_local[0]} is suitable for this call site."
                )
                lines.append(
                    f"   - Quality delta vs Haiku: {score_diff:+.2f}"
                )
                lines.append(
                    f"   - Latency: {best_local[1].avg_latency_ms:.0f}ms "
                    f"({latency_ratio:.1f}x vs Haiku)"
                )
                lines.append(f"   - Cost: FREE (local inference)")
            elif score_diff >= -0.2:
                lines.append(
                    f"⚠️ **TEST MORE**: {best_local[0]} shows promise but needs more testing."
                )
                lines.append(f"   - Quality delta vs Haiku: {score_diff:+.2f}")
            else:
                lines.append(
                    f"❌ **KEEP HAIKU**: Local models underperform significantly."
                )
                lines.append(f"   - Best local score: {best_local[1].avg_overall:.2f}")
                lines.append(f"   - Haiku score: {haiku_summary.avg_overall:.2f}")

    # Detailed results
    lines.extend([
        f"",
        f"## Detailed Model Statistics",
        f"",
    ])

    for name, summary in sorted_models:
        lines.extend([
            f"### {name}",
            f"",
            f"- Provider: {summary.provider}",
            f"- Model ID: `{summary.model_id}`",
            f"- Runs: {summary.successful_runs}/{summary.total_runs} successful",
            f"- Average latency: {summary.avg_latency_ms:.0f}ms",
            f"- Tokens/second: {summary.avg_tokens_per_second:.0f}",
            f"- Total tokens: {summary.total_input_tokens} in, {summary.total_output_tokens} out",
            f"",
        ])

        if summary.json_valid_rate > 0:
            lines.extend([
                f"**JSON Performance:**",
                f"- Valid JSON rate: {summary.json_valid_rate * 100:.0f}%",
                f"- Schema compliance: {summary.json_schema_valid_rate * 100:.0f}%",
                f"",
            ])

    # Sample outputs
    lines.extend([
        f"## Sample Outputs",
        f"",
        f"First capture, all models:",
        f"",
    ])

    if results:
        first_result = results[0]
        lines.append(f"**Input prompt (truncated):**")
        lines.append(f"```")
        lines.append(first_result.capture.user_prompt[:500] + "...")
        lines.append(f"```")
        lines.append(f"")

        for output in first_result.outputs:
            lines.append(f"**{output.model_name}:**")
            lines.append(f"```")
            lines.append(output.output[:500] + ("..." if len(output.output) > 500 else ""))
            lines.append(f"```")
            lines.append(f"")

    report = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)

    return report


def generate_migration_matrix(
    results_by_call_site: dict[str, list[BenchmarkResult]],
    output_path: Optional[Path] = None,
) -> str:
    """
    Generate a migration decision matrix across all call sites.

    Returns markdown report text.
    """
    lines = [
        "# LLM Migration Decision Matrix",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Call Site | Recommended Model | Score | Haiku Score | Delta | Decision |",
        "|-----------|-------------------|-------|-------------|-------|----------|",
    ]

    decisions = []

    for call_site, results in sorted(results_by_call_site.items()):
        scorer = get_scorer(call_site)

        # Calculate scores per model
        model_scores: dict[str, list[float]] = {}
        for result in results:
            for output in result.outputs:
                score = scorer(output, result.capture)
                if output.model_name not in model_scores:
                    model_scores[output.model_name] = []
                model_scores[output.model_name].append(score.overall)

        # Average scores
        avg_scores = {
            name: sum(scores) / len(scores)
            for name, scores in model_scores.items()
            if scores
        }

        if not avg_scores:
            continue

        # Find best and Haiku score
        best_model = max(avg_scores.items(), key=lambda x: x[1])
        haiku_score = avg_scores.get("Haiku 4.5", 0)

        # Find best local
        local_scores = {
            k: v for k, v in avg_scores.items() if k not in ("Haiku 4.5", "Sonnet 4", "GPT-4o Mini")
        }
        best_local = max(local_scores.items(), key=lambda x: x[1]) if local_scores else None

        # Decision
        if best_local:
            delta = best_local[1] - haiku_score
            if delta >= -0.1 and best_local[1] >= 0.7:
                decision = "✅ MIGRATE"
                rec_model = best_local[0]
            elif delta >= -0.2:
                decision = "⚠️ TEST"
                rec_model = best_local[0]
            else:
                decision = "❌ KEEP"
                rec_model = "Haiku 4.5"
        else:
            delta = 0
            decision = "❌ KEEP"
            rec_model = "Haiku 4.5"

        lines.append(
            f"| {call_site} | {rec_model} | "
            f"{best_local[1] if best_local else haiku_score:.2f} | "
            f"{haiku_score:.2f} | {delta:+.2f} | {decision} |"
        )

        decisions.append({
            "call_site": call_site,
            "recommended": rec_model,
            "decision": decision,
            "delta": delta,
        })

    lines.extend([
        "",
        "## Summary",
        "",
        f"- Total call sites: {len(decisions)}",
        f"- Ready to migrate: {sum(1 for d in decisions if '✅' in d['decision'])}",
        f"- Need more testing: {sum(1 for d in decisions if '⚠️' in d['decision'])}",
        f"- Keep on Haiku: {sum(1 for d in decisions if '❌' in d['decision'])}",
    ])

    report = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)

    return report
