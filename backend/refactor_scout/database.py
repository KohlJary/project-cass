"""
Scout Database - Track file metrics, extraction history, and health trends over time.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Literal

from .models import FileMetrics, ExtractionOpportunity


@dataclass
class ExtractionRecord:
    """Record of a single extraction operation."""
    date: str  # ISO format
    extraction_type: str  # "extract_class", "extract_functions", etc.
    extracted_to: str  # Target file path
    lines_moved: int
    items_extracted: List[str]  # Class/function names
    commit_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractionRecord":
        return cls(**data)


@dataclass
class FileRecord:
    """Historical record for a single file."""
    path: str
    last_scouted: Optional[str] = None  # ISO format
    last_metrics: Optional[dict] = None  # Serialized FileMetrics
    extraction_history: List[ExtractionRecord] = field(default_factory=list)
    metrics_history: List[dict] = field(default_factory=list)  # [{date, metrics}]

    @property
    def health_trend(self) -> Literal["improving", "stable", "degrading", "unknown"]:
        """Calculate health trend based on recent metrics history."""
        if len(self.metrics_history) < 2:
            return "unknown"

        # Compare last 3 snapshots (or fewer if not available)
        recent = self.metrics_history[-3:]

        if len(recent) < 2:
            return "unknown"

        # Calculate complexity scores
        scores = []
        for snapshot in recent:
            metrics = snapshot.get("metrics", {})
            score = metrics.get("complexity_score", 0.5)
            scores.append(score)

        # Determine trend
        if len(scores) >= 2:
            first_half = sum(scores[:len(scores)//2 + 1]) / (len(scores)//2 + 1)
            second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)

            diff = second_half - first_half
            if diff < -0.05:
                return "improving"
            elif diff > 0.05:
                return "degrading"

        return "stable"

    @property
    def days_since_last_scout(self) -> Optional[int]:
        """Days since this file was last scouted."""
        if not self.last_scouted:
            return None

        last = datetime.fromisoformat(self.last_scouted)
        now = datetime.now()
        return (now - last).days

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "last_scouted": self.last_scouted,
            "last_metrics": self.last_metrics,
            "extraction_history": [e.to_dict() for e in self.extraction_history],
            "metrics_history": self.metrics_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileRecord":
        extraction_history = [
            ExtractionRecord.from_dict(e)
            for e in data.get("extraction_history", [])
        ]
        return cls(
            path=data["path"],
            last_scouted=data.get("last_scouted"),
            last_metrics=data.get("last_metrics"),
            extraction_history=extraction_history,
            metrics_history=data.get("metrics_history", []),
        )


@dataclass
class ScoutSnapshot:
    """A point-in-time snapshot of codebase health."""
    date: str  # ISO format
    total_files: int
    healthy_files: int
    needs_attention: int
    critical_files: int
    overall_score: int  # 0-100
    total_lines: int
    avg_file_size: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScoutSnapshot":
        return cls(**data)


class ScoutDatabase:
    """
    Persistent storage for Scout metrics and history.

    Stores data in JSON files under data/scout/:
    - files.json - Per-file records
    - snapshots.json - Codebase-wide snapshots over time
    - config.json - Runtime configuration overrides
    """

    def __init__(self, data_dir: str = "data/scout"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.files_path = self.data_dir / "files.json"
        self.snapshots_path = self.data_dir / "snapshots.json"
        self.config_path = self.data_dir / "config.json"

        self._files: Dict[str, FileRecord] = {}
        self._snapshots: List[ScoutSnapshot] = []
        self._config: dict = {}

        self._load()

    def _load(self):
        """Load data from disk."""
        # Load file records
        if self.files_path.exists():
            with open(self.files_path) as f:
                data = json.load(f)
                self._files = {
                    path: FileRecord.from_dict(record)
                    for path, record in data.items()
                }

        # Load snapshots
        if self.snapshots_path.exists():
            with open(self.snapshots_path) as f:
                data = json.load(f)
                self._snapshots = [ScoutSnapshot.from_dict(s) for s in data]

        # Load config
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._config = json.load(f)

    def _save_files(self):
        """Save file records to disk."""
        data = {path: record.to_dict() for path, record in self._files.items()}
        with open(self.files_path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_snapshots(self):
        """Save snapshots to disk."""
        data = [s.to_dict() for s in self._snapshots]
        with open(self.snapshots_path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_config(self):
        """Save config to disk."""
        with open(self.config_path, "w") as f:
            json.dump(self._config, f, indent=2)

    # File record operations

    def get_file(self, path: str) -> Optional[FileRecord]:
        """Get record for a specific file."""
        # Normalize path
        path = str(Path(path).resolve())
        return self._files.get(path)

    def get_or_create_file(self, path: str) -> FileRecord:
        """Get or create record for a file."""
        path = str(Path(path).resolve())
        if path not in self._files:
            self._files[path] = FileRecord(path=path)
        return self._files[path]

    def record_scout(self, path: str, metrics: FileMetrics):
        """Record that a file was scouted with given metrics."""
        record = self.get_or_create_file(path)
        now = datetime.now().isoformat()

        record.last_scouted = now
        record.last_metrics = {
            "line_count": metrics.line_count,
            "function_count": metrics.function_count,
            "class_count": metrics.class_count,
            "import_count": metrics.import_count,
            "complexity_score": metrics.complexity_score,
            "avg_function_length": metrics.avg_function_length,
            "max_function_length": metrics.max_function_length,
        }

        # Add to metrics history (keep last 20 snapshots per file)
        record.metrics_history.append({
            "date": now,
            "metrics": record.last_metrics,
        })
        if len(record.metrics_history) > 20:
            record.metrics_history = record.metrics_history[-20:]

        self._save_files()

    def record_extraction(
        self,
        source_path: str,
        extraction_type: str,
        target_path: str,
        lines_moved: int,
        items_extracted: List[str],
        commit_hash: Optional[str] = None,
    ):
        """Record an extraction operation."""
        record = self.get_or_create_file(source_path)

        extraction = ExtractionRecord(
            date=datetime.now().isoformat(),
            extraction_type=extraction_type,
            extracted_to=target_path,
            lines_moved=lines_moved,
            items_extracted=items_extracted,
            commit_hash=commit_hash,
        )

        record.extraction_history.append(extraction)
        self._save_files()

    def should_scout(self, path: str, cooldown_days: int = 7) -> tuple[bool, str]:
        """
        Check if a file should be scouted based on cooldown.

        Returns (should_scout, reason).
        """
        record = self.get_file(path)

        if record is None:
            return True, "File has never been scouted"

        if record.last_scouted is None:
            return True, "File has never been scouted"

        days = record.days_since_last_scout
        if days is None:
            return True, "Could not determine last scout time"

        if days >= cooldown_days:
            return True, f"Last scouted {days} days ago (cooldown: {cooldown_days})"

        return False, f"Recently scouted ({days} days ago, cooldown: {cooldown_days})"

    def get_files_needing_scout(self, cooldown_days: int = 7) -> List[str]:
        """Get list of files that haven't been scouted recently."""
        needs_scout = []
        for path, record in self._files.items():
            should, _ = self.should_scout(path, cooldown_days)
            if should:
                needs_scout.append(path)
        return needs_scout

    # Snapshot operations

    def record_snapshot(
        self,
        total_files: int,
        healthy_files: int,
        needs_attention: int,
        critical_files: int,
        overall_score: int,
        total_lines: int,
        avg_file_size: float,
    ):
        """Record a codebase-wide health snapshot."""
        snapshot = ScoutSnapshot(
            date=datetime.now().isoformat(),
            total_files=total_files,
            healthy_files=healthy_files,
            needs_attention=needs_attention,
            critical_files=critical_files,
            overall_score=overall_score,
            total_lines=total_lines,
            avg_file_size=avg_file_size,
        )

        self._snapshots.append(snapshot)

        # Keep last 100 snapshots
        if len(self._snapshots) > 100:
            self._snapshots = self._snapshots[-100:]

        self._save_snapshots()

    def get_snapshots(self, limit: int = 10) -> List[ScoutSnapshot]:
        """Get recent snapshots."""
        return self._snapshots[-limit:]

    def get_health_trend(self) -> Literal["improving", "stable", "degrading", "unknown"]:
        """Calculate overall codebase health trend."""
        if len(self._snapshots) < 2:
            return "unknown"

        recent = self._snapshots[-5:]
        if len(recent) < 2:
            return "unknown"

        scores = [s.overall_score for s in recent]

        first_half = sum(scores[:len(scores)//2 + 1]) / (len(scores)//2 + 1)
        second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)

        diff = second_half - first_half
        if diff > 3:
            return "improving"
        elif diff < -3:
            return "degrading"

        return "stable"

    # Statistics

    def get_extraction_stats(self) -> dict:
        """Get aggregate extraction statistics."""
        total_extractions = 0
        total_lines_moved = 0
        extractions_by_type: Dict[str, int] = {}

        for record in self._files.values():
            for extraction in record.extraction_history:
                total_extractions += 1
                total_lines_moved += extraction.lines_moved
                ext_type = extraction.extraction_type
                extractions_by_type[ext_type] = extractions_by_type.get(ext_type, 0) + 1

        return {
            "total_extractions": total_extractions,
            "total_lines_moved": total_lines_moved,
            "extractions_by_type": extractions_by_type,
            "files_with_extractions": sum(
                1 for r in self._files.values() if r.extraction_history
            ),
        }

    def get_file_stats(self) -> dict:
        """Get aggregate file statistics."""
        total_files = len(self._files)

        trends = {"improving": 0, "stable": 0, "degrading": 0, "unknown": 0}
        for record in self._files.values():
            trends[record.health_trend] += 1

        return {
            "total_tracked_files": total_files,
            "health_trends": trends,
        }

    # Reporting

    def generate_history_report(self, path: str) -> Optional[str]:
        """Generate a history report for a specific file."""
        record = self.get_file(path)
        if not record:
            return None

        lines = [
            f"Scout History: {path}",
            "=" * 60,
            "",
        ]

        if record.last_scouted:
            lines.append(f"Last Scouted: {record.last_scouted}")
            lines.append(f"Days Since Scout: {record.days_since_last_scout}")
        else:
            lines.append("Never scouted")

        lines.append(f"Health Trend: {record.health_trend}")
        lines.append("")

        if record.last_metrics:
            lines.append("Current Metrics:")
            for key, value in record.last_metrics.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        if record.extraction_history:
            lines.append(f"Extraction History ({len(record.extraction_history)} total):")
            for ext in record.extraction_history[-5:]:  # Show last 5
                lines.append(f"  [{ext.date[:10]}] {ext.extraction_type}")
                lines.append(f"    → {ext.extracted_to} ({ext.lines_moved} lines)")
                lines.append(f"    Items: {', '.join(ext.items_extracted)}")
            lines.append("")

        if record.metrics_history:
            lines.append(f"Metrics History ({len(record.metrics_history)} snapshots):")
            for snapshot in record.metrics_history[-5:]:  # Show last 5
                date = snapshot["date"][:10]
                metrics = snapshot["metrics"]
                lines.append(
                    f"  [{date}] {metrics['line_count']} lines, "
                    f"complexity: {metrics['complexity_score']:.2f}"
                )

        return "\n".join(lines)

    def generate_dashboard(self) -> str:
        """Generate a text dashboard of codebase health."""
        lines = [
            "Scout Dashboard",
            "=" * 60,
            "",
        ]

        # Overall trend
        trend = self.get_health_trend()
        trend_symbol = {"improving": "↑", "stable": "→", "degrading": "↓", "unknown": "?"}
        lines.append(f"Overall Trend: {trend} {trend_symbol[trend]}")
        lines.append("")

        # Recent snapshots
        snapshots = self.get_snapshots(5)
        if snapshots:
            lines.append("Recent Health Scores:")
            for s in snapshots:
                date = s.date[:10]
                lines.append(
                    f"  [{date}] Score: {s.overall_score}/100 | "
                    f"Files: {s.total_files} | "
                    f"Critical: {s.critical_files}"
                )
            lines.append("")

        # Extraction stats
        ext_stats = self.get_extraction_stats()
        if ext_stats["total_extractions"] > 0:
            lines.append("Extraction Statistics:")
            lines.append(f"  Total Extractions: {ext_stats['total_extractions']}")
            lines.append(f"  Total Lines Moved: {ext_stats['total_lines_moved']}")
            lines.append(f"  Files Improved: {ext_stats['files_with_extractions']}")
            if ext_stats["extractions_by_type"]:
                lines.append("  By Type:")
                for ext_type, count in ext_stats["extractions_by_type"].items():
                    lines.append(f"    {ext_type}: {count}")
            lines.append("")

        # File stats
        file_stats = self.get_file_stats()
        lines.append("File Health Trends:")
        trends = file_stats["health_trends"]
        lines.append(f"  Improving: {trends['improving']}")
        lines.append(f"  Stable: {trends['stable']}")
        lines.append(f"  Degrading: {trends['degrading']}")
        lines.append(f"  Unknown: {trends['unknown']}")

        return "\n".join(lines)
