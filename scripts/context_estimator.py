#!/usr/bin/env python3
"""
Context Usage Estimator for Claude Code Sessions

Estimates and tracks token consumption during Claude Code sessions.
Helps understand what operations consume the most context.

Usage:
    # Record operations
    python context_estimator.py record file_read --content "$(cat somefile.py)"
    python context_estimator.py record bash_output --content "$(ls -la)"
    python context_estimator.py record tool_result --name "Grep" --content "matches..."

    # View current session stats
    python context_estimator.py stats
    python context_estimator.py stats --detailed

    # Reset session
    python context_estimator.py reset

    # Estimate tokens for arbitrary content
    python context_estimator.py estimate "some text content"
    python context_estimator.py estimate --file somefile.py
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Try to use tiktoken for accurate estimates, fall back to heuristic
try:
    import tiktoken
    ENCODER = tiktoken.encoding_for_model("gpt-4")  # Claude uses similar tokenization
    USE_TIKTOKEN = True
except ImportError:
    ENCODER = None
    USE_TIKTOKEN = False


# Session data location
SESSION_FILE = Path.home() / ".cache" / "claude-code" / "context_session.json"


@dataclass
class ContextOperation:
    """A single context-consuming operation."""
    op_type: str  # file_read, bash_output, tool_result, user_message, system_prompt
    tokens: int
    chars: int
    timestamp: str
    metadata: dict = field(default_factory=dict)  # tool name, file path, etc.


@dataclass
class SessionStats:
    """Cumulative session statistics."""
    session_id: str
    started_at: str
    operations: list[dict] = field(default_factory=list)

    # Totals by category
    totals: dict = field(default_factory=lambda: {
        "file_read": {"count": 0, "tokens": 0, "chars": 0},
        "bash_output": {"count": 0, "tokens": 0, "chars": 0},
        "tool_result": {"count": 0, "tokens": 0, "chars": 0},
        "user_message": {"count": 0, "tokens": 0, "chars": 0},
        "system_prompt": {"count": 0, "tokens": 0, "chars": 0},
        "other": {"count": 0, "tokens": 0, "chars": 0},
    })

    @property
    def total_tokens(self) -> int:
        return sum(cat["tokens"] for cat in self.totals.values())

    @property
    def total_operations(self) -> int:
        return sum(cat["count"] for cat in self.totals.values())


def estimate_tokens(content: str) -> int:
    """
    Estimate token count for content.
    Uses tiktoken if available, otherwise chars/4 heuristic.
    """
    if not content:
        return 0

    if USE_TIKTOKEN and ENCODER:
        return len(ENCODER.encode(content))
    else:
        # Heuristic: ~4 chars per token on average
        # Slightly more accurate: account for code having more tokens per char
        return max(1, len(content) // 4)


def estimate_tokens_detailed(content: str) -> tuple[int, str]:
    """Return token estimate and method used."""
    tokens = estimate_tokens(content)
    method = "tiktoken" if USE_TIKTOKEN else "heuristic (chars/4)"
    return tokens, method


def _default_totals() -> dict:
    """Default totals structure."""
    return {
        "file_read": {"count": 0, "tokens": 0, "chars": 0},
        "bash_output": {"count": 0, "tokens": 0, "chars": 0},
        "tool_result": {"count": 0, "tokens": 0, "chars": 0},
        "user_message": {"count": 0, "tokens": 0, "chars": 0},
        "system_prompt": {"count": 0, "tokens": 0, "chars": 0},
        "other": {"count": 0, "tokens": 0, "chars": 0},
    }


def load_session() -> SessionStats:
    """Load current session from disk, or create new."""
    if SESSION_FILE.exists():
        try:
            data = json.loads(SESSION_FILE.read_text())
            stats = SessionStats(
                session_id=data.get("session_id", "unknown"),
                started_at=data.get("started_at", datetime.now().isoformat()),
                operations=data.get("operations", []),
                totals=data.get("totals", _default_totals()),
            )
            return stats
        except (json.JSONDecodeError, KeyError):
            pass

    # Create new session
    return SessionStats(
        session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
        started_at=datetime.now().isoformat(),
    )


def save_session(stats: SessionStats) -> None:
    """Persist session to disk."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(asdict(stats), indent=2))


def record_operation(
    op_type: str,
    content: str,
    metadata: Optional[dict] = None
) -> ContextOperation:
    """Record a context-consuming operation."""
    tokens = estimate_tokens(content)
    chars = len(content)

    op = ContextOperation(
        op_type=op_type,
        tokens=tokens,
        chars=chars,
        timestamp=datetime.now().isoformat(),
        metadata=metadata or {},
    )

    # Update session
    stats = load_session()
    stats.operations.append(asdict(op))

    # Update category totals
    category = op_type if op_type in stats.totals else "other"
    stats.totals[category]["count"] += 1
    stats.totals[category]["tokens"] += tokens
    stats.totals[category]["chars"] += chars

    save_session(stats)
    return op


def get_stats(detailed: bool = False) -> dict:
    """Get current session statistics."""
    stats = load_session()

    result = {
        "session_id": stats.session_id,
        "started_at": stats.started_at,
        "estimation_method": "tiktoken" if USE_TIKTOKEN else "heuristic",
        "total_tokens": stats.total_tokens,
        "total_operations": stats.total_operations,
        "breakdown": stats.totals,
    }

    if detailed:
        result["recent_operations"] = stats.operations[-20:]  # Last 20 ops

    return result


def reset_session() -> None:
    """Reset session statistics."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def format_stats_table(stats: dict) -> str:
    """Format stats as a readable table."""
    lines = []
    lines.append(f"Session: {stats['session_id']}")
    lines.append(f"Started: {stats['started_at']}")
    lines.append(f"Method: {stats['estimation_method']}")
    lines.append("")
    lines.append("=" * 55)
    lines.append(f"{'Category':<15} {'Count':>8} {'Tokens':>12} {'Chars':>12}")
    lines.append("-" * 55)

    for category, data in stats["breakdown"].items():
        if data["count"] > 0:
            lines.append(
                f"{category:<15} {data['count']:>8} {data['tokens']:>12,} {data['chars']:>12,}"
            )

    lines.append("-" * 55)
    lines.append(f"{'TOTAL':<15} {stats['total_operations']:>8} {stats['total_tokens']:>12,}")
    lines.append("=" * 55)

    # Context usage indicator
    total = stats['total_tokens']
    if total < 50000:
        usage = "LOW"
    elif total < 100000:
        usage = "MODERATE"
    elif total < 150000:
        usage = "HIGH"
    else:
        usage = "CRITICAL"

    lines.append(f"\nContext Usage: {usage} ({total:,} tokens)")

    # Rough percentage of typical Claude context
    pct = (total / 200000) * 100  # Assume 200k context window
    lines.append(f"Estimated Context Fill: ~{pct:.1f}% of 200k window")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Context usage estimator for Claude Code sessions"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # record command
    record_parser = subparsers.add_parser("record", help="Record an operation")
    record_parser.add_argument(
        "op_type",
        choices=["file_read", "bash_output", "tool_result", "user_message", "system_prompt", "other"],
        help="Type of operation"
    )
    record_parser.add_argument("--content", "-c", help="Content to measure")
    record_parser.add_argument("--file", "-f", help="Read content from file")
    record_parser.add_argument("--name", "-n", help="Tool or file name (metadata)")
    record_parser.add_argument("--stdin", action="store_true", help="Read content from stdin")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show session statistics")
    stats_parser.add_argument("--detailed", "-d", action="store_true", help="Show recent operations")
    stats_parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # reset command
    subparsers.add_parser("reset", help="Reset session statistics")

    # estimate command
    estimate_parser = subparsers.add_parser("estimate", help="Estimate tokens for content")
    estimate_parser.add_argument("content", nargs="?", help="Content to estimate")
    estimate_parser.add_argument("--file", "-f", help="Read content from file")
    estimate_parser.add_argument("--stdin", action="store_true", help="Read content from stdin")

    args = parser.parse_args()

    if args.command == "record":
        # Get content from various sources
        content = ""
        if args.stdin:
            content = sys.stdin.read()
        elif args.file:
            content = Path(args.file).read_text()
        elif args.content:
            content = args.content
        else:
            print("Error: Must provide --content, --file, or --stdin", file=sys.stderr)
            sys.exit(1)

        metadata = {}
        if args.name:
            metadata["name"] = args.name

        op = record_operation(args.op_type, content, metadata)
        print(f"Recorded: {op.op_type} - {op.tokens:,} tokens ({op.chars:,} chars)")

    elif args.command == "stats":
        stats = get_stats(detailed=args.detailed)
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(format_stats_table(stats))
            if args.detailed and stats.get("recent_operations"):
                print("\nRecent Operations:")
                for op in stats["recent_operations"][-10:]:
                    name = op.get("metadata", {}).get("name", "")
                    name_str = f" ({name})" if name else ""
                    print(f"  {op['op_type']}{name_str}: {op['tokens']:,} tokens")

    elif args.command == "reset":
        reset_session()
        print("Session reset.")

    elif args.command == "estimate":
        content = ""
        if args.stdin:
            content = sys.stdin.read()
        elif args.file:
            content = Path(args.file).read_text()
        elif args.content:
            content = args.content
        else:
            print("Error: Must provide content, --file, or --stdin", file=sys.stderr)
            sys.exit(1)

        tokens, method = estimate_tokens_detailed(content)
        print(f"Tokens: {tokens:,} ({method})")
        print(f"Characters: {len(content):,}")

    else:
        parser.print_help()


# Programmatic API for use in other scripts
class ContextTracker:
    """Context tracker for programmatic use."""

    def __init__(self):
        self._stats = load_session()

    def record_file_read(self, content: str, path: Optional[str] = None) -> int:
        """Record a file read operation. Returns token count."""
        op = record_operation("file_read", content, {"name": path} if path else {})
        return op.tokens

    def record_bash_output(self, content: str, command: Optional[str] = None) -> int:
        """Record bash command output. Returns token count."""
        op = record_operation("bash_output", content, {"name": command} if command else {})
        return op.tokens

    def record_tool_result(self, content: str, tool_name: Optional[str] = None) -> int:
        """Record a tool result. Returns token count."""
        op = record_operation("tool_result", content, {"name": tool_name} if tool_name else {})
        return op.tokens

    def record_user_message(self, content: str) -> int:
        """Record a user message. Returns token count."""
        op = record_operation("user_message", content)
        return op.tokens

    def record_system_prompt(self, content: str, name: Optional[str] = None) -> int:
        """Record system prompt content. Returns token count."""
        op = record_operation("system_prompt", content, {"name": name} if name else {})
        return op.tokens

    @property
    def total_tokens(self) -> int:
        """Get total tokens used in session."""
        return load_session().total_tokens

    def get_breakdown(self) -> dict:
        """Get token breakdown by category."""
        return load_session().totals

    def reset(self) -> None:
        """Reset the session."""
        reset_session()


if __name__ == "__main__":
    main()
