"""
Cass Vessel - GitHub Metrics Manager
Tracks repository metrics (clones, traffic, stars, forks) with historical storage.
GitHub only retains 14 days of traffic data, so we persist daily snapshots.
"""
import os
import json
import logging
import httpx
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field

logger = logging.getLogger("cass-vessel")

# Default repos to track
DEFAULT_REPOS = [
    "KohlJary/Temple-Codex",
    "KohlJary/project-cass"
]


@dataclass
class RepoMetrics:
    """Metrics for a single repository."""
    repo: str
    clones_count: int = 0
    clones_uniques: int = 0
    views_count: int = 0
    views_uniques: int = 0
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    # Daily breakdown from GitHub (last 14 days)
    clones_daily: List[Dict[str, Any]] = field(default_factory=list)
    views_daily: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MetricsSnapshot:
    """A point-in-time snapshot of all tracked repos."""
    timestamp: str
    repos: Dict[str, Dict[str, Any]]
    api_calls_remaining: Optional[int] = None
    error: Optional[str] = None


class GitHubMetricsManager:
    """
    Manages GitHub metrics fetching and historical storage.

    Storage structure:
        data/github/
            current.json          - Latest snapshot
            historical/
                2025-12-09.json   - Daily snapshots
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "github"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.historical_dir = self.data_dir / "historical"
        self.historical_dir.mkdir(exist_ok=True)

        self.current_file = self.data_dir / "current.json"

        # GitHub API config
        self.token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_KEY")
        repos_env = os.getenv("GITHUB_REPOS")
        self.repos = repos_env.split(",") if repos_env else DEFAULT_REPOS

        self.base_url = "https://api.github.com"
        self.last_fetch: Optional[datetime] = None
        self.rate_limit_remaining: Optional[int] = None

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """
        Get headers for GitHub API requests.

        Args:
            token: Optional override token. If not provided, uses the system default.
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Cass-Vessel-Metrics"
        }
        effective_token = token or self.token
        if effective_token:
            headers["Authorization"] = f"token {effective_token}"
        return headers

    async def fetch_repo_metrics(self, repo: str, token: Optional[str] = None) -> RepoMetrics:
        """
        Fetch all metrics for a single repository.

        Args:
            repo: Repository in "owner/repo" format
            token: Optional PAT to use instead of system default
        """
        metrics = RepoMetrics(repo=repo)
        headers = self._get_headers(token)

        async with httpx.AsyncClient() as client:
            # Basic repo info (stars, forks, watchers, issues)
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{repo}",
                    headers=headers,
                    timeout=30.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    metrics.stars = data.get("stargazers_count", 0)
                    metrics.forks = data.get("forks_count", 0)
                    metrics.watchers = data.get("subscribers_count", 0)  # True watchers
                    metrics.open_issues = data.get("open_issues_count", 0)

                    # Track rate limit
                    self.rate_limit_remaining = int(resp.headers.get("X-RateLimit-Remaining", 0))
                else:
                    logger.warning(f"Failed to fetch repo info for {repo}: {resp.status_code}")
            except Exception as e:
                logger.error(f"Error fetching repo info for {repo}: {e}")

            # Clone stats (requires push access)
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{repo}/traffic/clones",
                    headers=headers,
                    timeout=30.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    metrics.clones_count = data.get("count", 0)
                    metrics.clones_uniques = data.get("uniques", 0)
                    metrics.clones_daily = data.get("clones", [])
                elif resp.status_code == 403:
                    logger.warning(f"No access to clone stats for {repo} (need push access)")
                else:
                    logger.warning(f"Failed to fetch clone stats for {repo}: {resp.status_code}")
            except Exception as e:
                logger.error(f"Error fetching clone stats for {repo}: {e}")

            # Traffic/views stats (requires push access)
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{repo}/traffic/views",
                    headers=headers,
                    timeout=30.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    metrics.views_count = data.get("count", 0)
                    metrics.views_uniques = data.get("uniques", 0)
                    metrics.views_daily = data.get("views", [])
                elif resp.status_code == 403:
                    logger.warning(f"No access to traffic stats for {repo} (need push access)")
                else:
                    logger.warning(f"Failed to fetch traffic stats for {repo}: {resp.status_code}")
            except Exception as e:
                logger.error(f"Error fetching traffic stats for {repo}: {e}")

        return metrics

    async def fetch_all_metrics(self) -> MetricsSnapshot:
        """Fetch metrics for all tracked repositories."""
        timestamp = datetime.now().isoformat()
        repos_data = {}
        error = None

        for repo in self.repos:
            try:
                metrics = await self.fetch_repo_metrics(repo)
                repos_data[repo] = asdict(metrics)
            except Exception as e:
                logger.error(f"Failed to fetch metrics for {repo}: {e}")
                error = str(e) if not error else f"{error}; {e}"

        snapshot = MetricsSnapshot(
            timestamp=timestamp,
            repos=repos_data,
            api_calls_remaining=self.rate_limit_remaining,
            error=error
        )

        self.last_fetch = datetime.now()
        return snapshot

    def save_snapshot(self, snapshot: MetricsSnapshot):
        """Save snapshot to current.json and daily historical file."""
        data = asdict(snapshot)

        # Save current
        with open(self.current_file, 'w') as f:
            json.dump(data, f, indent=2)

        # Save to historical (one file per day)
        date_str = datetime.now().strftime("%Y-%m-%d")
        historical_file = self.historical_dir / f"{date_str}.json"

        # Append to or create daily file
        daily_data = []
        if historical_file.exists():
            try:
                with open(historical_file, 'r') as f:
                    daily_data = json.load(f)
                    if not isinstance(daily_data, list):
                        daily_data = [daily_data]
            except:
                daily_data = []

        daily_data.append(data)

        with open(historical_file, 'w') as f:
            json.dump(daily_data, f, indent=2)

        logger.info(f"Saved GitHub metrics snapshot at {snapshot.timestamp}")

    async def refresh_metrics(self) -> MetricsSnapshot:
        """Fetch and save fresh metrics."""
        snapshot = await self.fetch_all_metrics()
        self.save_snapshot(snapshot)
        return snapshot

    def get_current_metrics(self) -> Optional[Dict[str, Any]]:
        """Get the most recent metrics snapshot."""
        if not self.current_file.exists():
            return None

        try:
            with open(self.current_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading current metrics: {e}")
            return None

    def get_historical_metrics(
        self,
        days: int = 30,
        repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical metrics for the specified number of days.

        Args:
            days: Number of days of history to retrieve
            repo: Optional specific repo to filter for

        Returns:
            List of snapshots, oldest first
        """
        results = []
        today = datetime.now()

        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            historical_file = self.historical_dir / f"{date_str}.json"

            if historical_file.exists():
                try:
                    with open(historical_file, 'r') as f:
                        daily_data = json.load(f)
                        if isinstance(daily_data, list):
                            # Take the last snapshot of each day for summary
                            if daily_data:
                                snapshot = daily_data[-1]
                                if repo:
                                    # Filter to specific repo
                                    if repo in snapshot.get("repos", {}):
                                        results.append({
                                            "timestamp": snapshot["timestamp"],
                                            "date": date_str,
                                            "metrics": snapshot["repos"][repo]
                                        })
                                else:
                                    results.append({
                                        "timestamp": snapshot["timestamp"],
                                        "date": date_str,
                                        "repos": snapshot["repos"]
                                    })
                        else:
                            # Legacy single-snapshot format
                            if repo:
                                if repo in daily_data.get("repos", {}):
                                    results.append({
                                        "timestamp": daily_data["timestamp"],
                                        "date": date_str,
                                        "metrics": daily_data["repos"][repo]
                                    })
                            else:
                                results.append({
                                    "timestamp": daily_data["timestamp"],
                                    "date": date_str,
                                    "repos": daily_data["repos"]
                                })
                except Exception as e:
                    logger.error(f"Error loading historical data for {date_str}: {e}")

        # Return oldest first
        results.reverse()
        return results

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all repos and history."""
        current = self.get_current_metrics()
        history = self.get_historical_metrics(days=30)

        stats = {
            "tracked_repos": self.repos,
            "has_token": bool(self.token),
            "last_fetch": self.last_fetch.isoformat() if self.last_fetch else None,
            "rate_limit_remaining": self.rate_limit_remaining,
            "historical_days_available": len(history),
            "current": {}
        }

        if current:
            stats["current"]["timestamp"] = current.get("timestamp")
            stats["current"]["total_clones"] = sum(
                r.get("clones_count", 0) for r in current.get("repos", {}).values()
            )
            stats["current"]["total_unique_cloners"] = sum(
                r.get("clones_uniques", 0) for r in current.get("repos", {}).values()
            )
            stats["current"]["total_stars"] = sum(
                r.get("stars", 0) for r in current.get("repos", {}).values()
            )
            stats["current"]["total_forks"] = sum(
                r.get("forks", 0) for r in current.get("repos", {}).values()
            )

        return stats

    def get_time_series(
        self,
        metric: str,
        days: int = 14,
        repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get time series data for a specific metric.

        Args:
            metric: One of 'clones', 'clones_uniques', 'views', 'views_uniques', 'stars', 'forks'
            days: Number of days
            repo: Optional specific repo (if None, sums across all repos)

        Returns:
            List of {date, value} objects
        """
        metric_map = {
            "clones": "clones_count",
            "clones_uniques": "clones_uniques",
            "views": "views_count",
            "views_uniques": "views_uniques",
            "stars": "stars",
            "forks": "forks"
        }

        field = metric_map.get(metric, metric)
        history = self.get_historical_metrics(days=days, repo=repo)

        series = []
        for entry in history:
            if repo:
                value = entry.get("metrics", {}).get(field, 0)
            else:
                # Sum across all repos
                value = sum(
                    r.get(field, 0) for r in entry.get("repos", {}).values()
                )
            series.append({
                "date": entry["date"],
                "value": value
            })

        return series

    async def fetch_project_metrics(
        self,
        github_repo: str,
        github_token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch metrics for a specific project's GitHub repository.

        This is designed to be called per-project, using the project's
        configured repo and optional project-specific PAT.

        Args:
            github_repo: Repository in "owner/repo" format
            github_token: Project-specific PAT, or None to use system default

        Returns:
            Metrics dict or None if fetch fails
        """
        if not github_repo:
            return None

        try:
            metrics = await self.fetch_repo_metrics(github_repo, token=github_token)
            return {
                "repo": metrics.repo,
                "stars": metrics.stars,
                "forks": metrics.forks,
                "watchers": metrics.watchers,
                "open_issues": metrics.open_issues,
                "clones_count": metrics.clones_count,
                "clones_uniques": metrics.clones_uniques,
                "views_count": metrics.views_count,
                "views_uniques": metrics.views_uniques,
                "last_updated": datetime.now().isoformat(),
                "using_project_token": github_token is not None,
            }
        except Exception as e:
            logger.error(f"Failed to fetch project metrics for {github_repo}: {e}")
            return None
