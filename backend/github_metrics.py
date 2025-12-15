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

    Storage: SQLite github_metrics table with daemon_id support.
    """

    def __init__(self, daemon_id: str = None, data_dir: Path = None):
        # data_dir kept for backwards compatibility but not used
        self._daemon_id = daemon_id
        if not self._daemon_id:
            self._load_default_daemon()

        # GitHub API config
        self.token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_KEY")
        repos_env = os.getenv("GITHUB_REPOS")
        self.repos = repos_env.split(",") if repos_env else DEFAULT_REPOS

        self.base_url = "https://api.github.com"
        self.last_fetch: Optional[datetime] = None
        self.rate_limit_remaining: Optional[int] = None

    def _load_default_daemon(self):
        """Load default daemon ID from database"""
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute("SELECT id FROM daemons LIMIT 1")
            row = cursor.fetchone()
            if row:
                self._daemon_id = row[0]

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
        """Save snapshot to SQLite database."""
        from database import get_db, json_serialize

        timestamp = snapshot.timestamp
        date_str = datetime.now().strftime("%Y-%m-%d")

        with get_db() as conn:
            conn.execute("""
                INSERT INTO github_metrics (
                    daemon_id, timestamp, date, repos_json,
                    api_calls_remaining, error
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                self._daemon_id,
                timestamp,
                date_str,
                json_serialize(snapshot.repos),
                snapshot.api_calls_remaining,
                snapshot.error
            ))
            conn.commit()

        logger.info(f"Saved GitHub metrics snapshot at {snapshot.timestamp}")

    async def refresh_metrics(self) -> MetricsSnapshot:
        """Fetch and save fresh metrics."""
        snapshot = await self.fetch_all_metrics()
        self.save_snapshot(snapshot)
        return snapshot

    def get_current_metrics(self) -> Optional[Dict[str, Any]]:
        """Get the most recent metrics snapshot."""
        from database import get_db, json_deserialize

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT timestamp, repos_json, api_calls_remaining, error
                FROM github_metrics
                WHERE daemon_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (self._daemon_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                "timestamp": row[0],
                "repos": json_deserialize(row[1]) or {},
                "api_calls_remaining": row[2],
                "error": row[3]
            }

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
            List of snapshots, oldest first (one per day, latest snapshot of each day)
        """
        from database import get_db, json_deserialize

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        with get_db() as conn:
            # Get the latest snapshot per day using GROUP BY
            # We use a subquery to get max timestamp per date, then join back
            cursor = conn.execute("""
                SELECT g.timestamp, g.date, g.repos_json
                FROM github_metrics g
                INNER JOIN (
                    SELECT date, MAX(timestamp) as max_ts
                    FROM github_metrics
                    WHERE daemon_id = ? AND date >= ?
                    GROUP BY date
                ) latest ON g.date = latest.date AND g.timestamp = latest.max_ts
                WHERE g.daemon_id = ?
                ORDER BY g.date ASC
            """, (self._daemon_id, cutoff_date, self._daemon_id))

            results = []
            for row in cursor.fetchall():
                repos_data = json_deserialize(row[2]) or {}
                date_str = row[1]
                timestamp = row[0]

                if repo:
                    # Filter to specific repo
                    if repo in repos_data:
                        results.append({
                            "timestamp": timestamp,
                            "date": date_str,
                            "metrics": repos_data[repo]
                        })
                else:
                    results.append({
                        "timestamp": timestamp,
                        "date": date_str,
                        "repos": repos_data
                    })

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
