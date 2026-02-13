#!/usr/bin/env python3
"""
Compare reading modes and models for world state consumption.

Tests all combinations of:
- Reading mode: progressive vs single_pass
- Model: claude-3-5-haiku vs claude-3-haiku

Usage:
    python -m world.compare_modes [--url URL] [--use-cached]
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add backend to path if running directly
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from world.models import Article, ProcessingStatus
from world.article_consumer import ArticleConsumer
from world.content_analyzer import ContentAnalyzer, ReadingMode


# Test configurations
CONFIGS = [
    {"mode": ReadingMode.PROGRESSIVE, "model": "claude-haiku-4-5-20251001", "label": "Progressive + Haiku 4.5"},
    {"mode": ReadingMode.SINGLE_PASS, "model": "claude-haiku-4-5-20251001", "label": "Single Pass + Haiku 4.5"},
    {"mode": ReadingMode.PROGRESSIVE, "model": "claude-3-5-haiku-20241022", "label": "Progressive + Haiku 3.5"},
    {"mode": ReadingMode.SINGLE_PASS, "model": "claude-3-5-haiku-20241022", "label": "Single Pass + Haiku 3.5"},
]


def get_test_article(url: Optional[str] = None, use_cached: bool = False) -> Article:
    """Get a test article, either from URL or cached content."""

    cache_path = Path("data/articles/test_article.json")

    if use_cached and cache_path.exists():
        print("Using cached test article...")
        with open(cache_path) as f:
            data = json.load(f)
        return Article(
            id="test-article",
            daemon_id="cass",
            url=data["url"],
            headline=data["headline"],
            source=data.get("source"),
            category=data.get("category"),
            full_content=data["content"],
            processing_status=ProcessingStatus.PENDING,
            consumed_at=datetime.now().isoformat(),
        )

    # Fetch fresh article
    if not url:
        # Try to get a headline from world state
        try:
            from sources.world_state_source import WorldStateSource
            ws = WorldStateSource(daemon_id="cass")
            rollups = ws.load_rollups()
            headlines = rollups.get("news", {}).get("headlines", [])
            if headlines:
                url = headlines[0].get("url")
                print(f"Using headline: {headlines[0].get('title', 'Unknown')[:60]}...")
        except Exception as e:
            print(f"Could not get headlines: {e}")

    if not url:
        # Use a known good test URL
        url = "https://arstechnica.com/science/2024/01/james-webb-space-telescope-reveals-new-details-about-early-universe/"
        print(f"Using default test URL")

    print(f"Fetching article from: {url}")

    consumer = ArticleConsumer("test-daemon")
    content = consumer.fetch_article_content(url)

    if not content:
        print("ERROR: Could not fetch article content")
        print("Please provide a URL with --url or ensure trafilatura is installed")
        sys.exit(1)

    article = Article(
        id="test-article",
        daemon_id="cass",
        url=url,
        headline="Test Article",
        source="Test Source",
        category="technology",
        full_content=content,
        processing_status=ProcessingStatus.PENDING,
        consumed_at=datetime.now().isoformat(),
    )

    # Cache for future runs
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({
            "url": url,
            "headline": article.headline,
            "source": article.source,
            "category": article.category,
            "content": content,
            "cached_at": datetime.now().isoformat(),
        }, f, indent=2)
    print(f"Cached article ({len(content)} chars)")

    return article


def run_comparison(article: Article):
    """Run all configurations and compare results."""

    results = []

    print(f"\n{'='*70}")
    print(f"ARTICLE: {article.headline[:60]}...")
    print(f"Content length: {len(article.full_content or '')} chars")
    print(f"{'='*70}\n")

    for config in CONFIGS:
        print(f"\n{'-'*50}")
        print(f"Testing: {config['label']}")
        print(f"{'-'*50}")

        analyzer = ContentAnalyzer(
            daemon_id="cass",
            reading_mode=config["mode"],
            model=config["model"],
        )

        start_time = time.time()

        try:
            insights = analyzer.analyze(article)
            elapsed = time.time() - start_time

            result = {
                "config": config["label"],
                "mode": config["mode"].value,
                "model": config["model"],
                "elapsed_seconds": round(elapsed, 2),
                "input_tokens": analyzer.total_input_tokens,
                "output_tokens": analyzer.total_output_tokens,
                "total_tokens": analyzer.total_input_tokens + analyzer.total_output_tokens,
                "summary_length": len(insights.summary),
                "observations": len(insights.observations),
                "questions": len(insights.questions),
                "opinions": len(insights.opinions),
                "growth_edges": len(insights.growth_edges),
                "insights": insights,
            }

            results.append(result)

            print(f"  Time: {elapsed:.1f}s")
            print(f"  Tokens: {result['total_tokens']} ({result['input_tokens']} in, {result['output_tokens']} out)")
            print(f"  Summary: {result['summary_length']} chars")
            print(f"  Extractions: {result['observations']} obs, {result['questions']} questions, {result['opinions']} opinions, {result['growth_edges']} edges")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "config": config["label"],
                "mode": config["mode"].value,
                "model": config["model"],
                "error": str(e),
            })

    return results


def print_detailed_comparison(results):
    """Print detailed comparison of all results."""

    print(f"\n{'='*70}")
    print("COMPARISON SUMMARY")
    print(f"{'='*70}\n")

    # Summary table
    print(f"{'Config':<35} {'Time':>8} {'Tokens':>8} {'Obs':>5} {'Ques':>5} {'Opin':>5} {'Edge':>5}")
    print("-" * 80)

    for r in results:
        if "error" in r:
            print(f"{r['config']:<35} ERROR: {r['error'][:30]}")
        else:
            print(f"{r['config']:<35} {r['elapsed_seconds']:>7.1f}s {r['total_tokens']:>8} {r['observations']:>5} {r['questions']:>5} {r['opinions']:>5} {r['growth_edges']:>5}")

    # Detailed extractions for each
    print(f"\n{'='*70}")
    print("DETAILED EXTRACTIONS")
    print(f"{'='*70}")

    for r in results:
        if "error" in r:
            continue

        print(f"\n\n{'#'*60}")
        print(f"# {r['config']}")
        print(f"{'#'*60}")

        insights = r["insights"]

        print(f"\n## Summary ({len(insights.summary)} chars)")
        print(insights.summary[:500] + "..." if len(insights.summary) > 500 else insights.summary)

        if insights.observations:
            print(f"\n## Observations ({len(insights.observations)})")
            for i, obs in enumerate(insights.observations):
                print(f"  {i+1}. [{obs.category}] {obs.text[:100]}... (conf: {obs.confidence:.1f})")

        if insights.questions:
            print(f"\n## Questions ({len(insights.questions)})")
            for i, q in enumerate(insights.questions):
                print(f"  {i+1}. [{q.question_type}] {q.question[:100]}... (imp: {q.importance:.1f})")

        if insights.opinions:
            print(f"\n## Opinions ({len(insights.opinions)})")
            for i, op in enumerate(insights.opinions):
                print(f"  {i+1}. {op.topic}: {op.position[:80]}... (conf: {op.confidence:.1f})")

        if insights.growth_edges:
            print(f"\n## Growth Edges ({len(insights.growth_edges)})")
            for i, ge in enumerate(insights.growth_edges):
                print(f"  {i+1}. {ge.area} (imp: {ge.importance:.1f})")


def main():
    parser = argparse.ArgumentParser(description="Compare world consumption reading modes")
    parser.add_argument("--url", help="Article URL to test with")
    parser.add_argument("--use-cached", action="store_true", help="Use cached test article if available")
    parser.add_argument("--output", help="Save results to JSON file")
    args = parser.parse_args()

    # Get test article
    article = get_test_article(url=args.url, use_cached=args.use_cached)

    # Run comparison
    results = run_comparison(article)

    # Print detailed comparison
    print_detailed_comparison(results)

    # Save to file if requested
    if args.output:
        output_data = []
        for r in results:
            if "insights" in r:
                r_copy = dict(r)
                r_copy["insights"] = {
                    "summary": r["insights"].summary,
                    "observations": [asdict(o) for o in r["insights"].observations],
                    "questions": [asdict(q) for q in r["insights"].questions],
                    "opinions": [asdict(o) for o in r["insights"].opinions],
                    "growth_edges": [asdict(g) for g in r["insights"].growth_edges],
                }
                output_data.append(r_copy)
            else:
                output_data.append(r)

        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
