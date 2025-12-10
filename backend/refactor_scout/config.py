"""
Scout Configuration - YAML-based configuration with per-directory overrides.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml

from .thresholds import DEFAULT_THRESHOLDS


@dataclass
class ThresholdConfig:
    """Threshold configuration."""
    max_lines: int = DEFAULT_THRESHOLDS["max_lines"]
    max_imports: int = DEFAULT_THRESHOLDS["max_imports"]
    max_functions: int = DEFAULT_THRESHOLDS["max_functions"]
    max_function_length: int = DEFAULT_THRESHOLDS["max_function_length"]
    max_classes_per_file: int = DEFAULT_THRESHOLDS["max_classes_per_file"]
    max_class_lines: int = DEFAULT_THRESHOLDS["max_class_lines"]
    complexity_warning: float = DEFAULT_THRESHOLDS["complexity_warning"]
    complexity_critical: float = DEFAULT_THRESHOLDS["complexity_critical"]
    scout_cooldown_days: int = 7

    def to_dict(self) -> dict:
        """Convert to threshold dict for ThresholdChecker."""
        return {
            "max_lines": self.max_lines,
            "max_imports": self.max_imports,
            "max_functions": self.max_functions,
            "max_function_length": self.max_function_length,
            "max_classes_per_file": self.max_classes_per_file,
            "max_class_lines": self.max_class_lines,
            "complexity_warning": self.complexity_warning,
            "complexity_critical": self.complexity_critical,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThresholdConfig":
        """Create from dict, using defaults for missing values."""
        return cls(
            max_lines=data.get("max_lines", DEFAULT_THRESHOLDS["max_lines"]),
            max_imports=data.get("max_imports", DEFAULT_THRESHOLDS["max_imports"]),
            max_functions=data.get("max_functions", DEFAULT_THRESHOLDS["max_functions"]),
            max_function_length=data.get("max_function_length", DEFAULT_THRESHOLDS["max_function_length"]),
            max_classes_per_file=data.get("max_classes_per_file", DEFAULT_THRESHOLDS["max_classes_per_file"]),
            max_class_lines=data.get("max_class_lines", DEFAULT_THRESHOLDS["max_class_lines"]),
            complexity_warning=data.get("complexity_warning", DEFAULT_THRESHOLDS["complexity_warning"]),
            complexity_critical=data.get("complexity_critical", DEFAULT_THRESHOLDS["complexity_critical"]),
            scout_cooldown_days=data.get("scout_cooldown_days", 7),
        )


@dataclass
class ExecutionConfig:
    """Execution behavior configuration."""
    max_extractions_per_scout: int = 3
    max_scout_duration_seconds: int = 900  # 15 minutes
    require_passing_tests: bool = True
    auto_rollback_on_failure: bool = True
    create_backups: bool = True
    verify_syntax: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionConfig":
        return cls(
            max_extractions_per_scout=data.get("max_extractions_per_scout", 3),
            max_scout_duration_seconds=data.get("max_scout_duration_seconds", 900),
            require_passing_tests=data.get("require_passing_tests", True),
            auto_rollback_on_failure=data.get("auto_rollback_on_failure", True),
            create_backups=data.get("create_backups", True),
            verify_syntax=data.get("verify_syntax", True),
        )


PolicyType = Literal["aggressive", "moderate", "conservative", "skip"]


@dataclass
class ScoutConfig:
    """
    Complete Scout configuration.

    Loaded from scout.yaml in project root or data/scout/config.yaml.
    """
    enabled: bool = True
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    default_policy: PolicyType = "moderate"
    directory_overrides: Dict[str, PolicyType] = field(default_factory=dict)
    excluded_patterns: List[str] = field(default_factory=lambda: [
        "**/test_*.py",
        "**/*_test.py",
        "**/tests/**",
        "**/migrations/**",
        "**/__pycache__/**",
        "**/venv/**",
        "**/.venv/**",
    ])

    def get_policy_for_path(self, path: str) -> PolicyType:
        """Get the policy that applies to a given path."""
        path = str(Path(path).resolve())

        # Check directory overrides (longest match wins)
        best_match = None
        best_match_len = 0

        for dir_pattern, policy in self.directory_overrides.items():
            # Normalize the pattern
            if not dir_pattern.startswith("/"):
                dir_pattern = f"**/{dir_pattern}"

            # Check if path is under this directory
            pattern_path = Path(dir_pattern.replace("**", "").strip("/"))
            if str(pattern_path) in path:
                match_len = len(str(pattern_path))
                if match_len > best_match_len:
                    best_match = policy
                    best_match_len = match_len

        return best_match or self.default_policy

    def should_skip_path(self, path: str) -> bool:
        """Check if a path should be skipped based on excluded patterns."""
        from fnmatch import fnmatch

        path_str = str(path)

        for pattern in self.excluded_patterns:
            # Handle ** patterns
            if "**" in pattern:
                # Simple ** handling - check if any part matches
                parts = pattern.split("**")
                if len(parts) == 2:
                    prefix, suffix = parts
                    prefix = prefix.strip("/")
                    suffix = suffix.strip("/")
                    if prefix and suffix:
                        if prefix in path_str and path_str.endswith(suffix):
                            return True
                    elif prefix:
                        if prefix in path_str:
                            return True
                    elif suffix:
                        if fnmatch(path_str, f"*{suffix}"):
                            return True
            else:
                if fnmatch(path_str, pattern):
                    return True

        return False

    def get_thresholds_for_policy(self, policy: PolicyType) -> ThresholdConfig:
        """Get adjusted thresholds based on policy."""
        base = self.thresholds

        if policy == "aggressive":
            # Lower thresholds = more aggressive refactoring
            return ThresholdConfig(
                max_lines=int(base.max_lines * 0.75),
                max_imports=int(base.max_imports * 0.75),
                max_functions=int(base.max_functions * 0.75),
                max_function_length=int(base.max_function_length * 0.75),
                max_classes_per_file=base.max_classes_per_file,
                max_class_lines=int(base.max_class_lines * 0.75),
                complexity_warning=base.complexity_warning - 0.1,
                complexity_critical=base.complexity_critical - 0.1,
                scout_cooldown_days=max(1, base.scout_cooldown_days // 2),
            )
        elif policy == "conservative":
            # Higher thresholds = less aggressive
            return ThresholdConfig(
                max_lines=int(base.max_lines * 1.5),
                max_imports=int(base.max_imports * 1.5),
                max_functions=int(base.max_functions * 1.5),
                max_function_length=int(base.max_function_length * 1.5),
                max_classes_per_file=base.max_classes_per_file + 1,
                max_class_lines=int(base.max_class_lines * 1.5),
                complexity_warning=min(0.9, base.complexity_warning + 0.1),
                complexity_critical=min(0.95, base.complexity_critical + 0.1),
                scout_cooldown_days=base.scout_cooldown_days * 2,
            )
        elif policy == "skip":
            # Return very high thresholds (effectively skip)
            return ThresholdConfig(
                max_lines=99999,
                max_imports=9999,
                max_functions=9999,
                max_function_length=9999,
                max_classes_per_file=9999,
                max_class_lines=99999,
                complexity_warning=1.0,
                complexity_critical=1.0,
                scout_cooldown_days=365,
            )

        # Default/moderate
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "ScoutConfig":
        """Create from dict."""
        thresholds = ThresholdConfig.from_dict(data.get("thresholds", {}))
        execution = ExecutionConfig.from_dict(data.get("execution", {}))

        return cls(
            enabled=data.get("enabled", True),
            thresholds=thresholds,
            execution=execution,
            default_policy=data.get("default_policy", "moderate"),
            directory_overrides=data.get("directory_overrides", {}),
            excluded_patterns=data.get("excluded_patterns", cls().excluded_patterns),
        )

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "enabled": self.enabled,
            "thresholds": {
                "max_lines": self.thresholds.max_lines,
                "max_imports": self.thresholds.max_imports,
                "max_functions": self.thresholds.max_functions,
                "max_function_length": self.thresholds.max_function_length,
                "max_classes_per_file": self.thresholds.max_classes_per_file,
                "max_class_lines": self.thresholds.max_class_lines,
                "complexity_warning": self.thresholds.complexity_warning,
                "complexity_critical": self.thresholds.complexity_critical,
                "scout_cooldown_days": self.thresholds.scout_cooldown_days,
            },
            "execution": {
                "max_extractions_per_scout": self.execution.max_extractions_per_scout,
                "max_scout_duration_seconds": self.execution.max_scout_duration_seconds,
                "require_passing_tests": self.execution.require_passing_tests,
                "auto_rollback_on_failure": self.execution.auto_rollback_on_failure,
                "create_backups": self.execution.create_backups,
                "verify_syntax": self.execution.verify_syntax,
            },
            "default_policy": self.default_policy,
            "directory_overrides": self.directory_overrides,
            "excluded_patterns": self.excluded_patterns,
        }


def load_config(config_path: Optional[str] = None) -> ScoutConfig:
    """
    Load Scout configuration from YAML file.

    Search order:
    1. Explicit config_path if provided
    2. scout.yaml in current directory
    3. .scout.yaml in current directory
    4. data/scout/config.yaml
    5. Default configuration
    """
    search_paths = []

    if config_path:
        search_paths.append(Path(config_path))

    # Add standard locations
    cwd = Path.cwd()
    search_paths.extend([
        cwd / "scout.yaml",
        cwd / ".scout.yaml",
        cwd / "data" / "scout" / "config.yaml",
    ])

    for path in search_paths:
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return ScoutConfig.from_dict(data)

    # Return default config
    return ScoutConfig()


def save_config(config: ScoutConfig, config_path: str = "scout.yaml"):
    """Save Scout configuration to YAML file."""
    with open(config_path, "w") as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)


def generate_default_config() -> str:
    """Generate default configuration as YAML string."""
    config = ScoutConfig()
    return yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False)
