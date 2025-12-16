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

    def cleanup_duplicate_snapshots(self) -> int:
        """
        Remove duplicate snapshots, keeping only the most recent per day.

        This saves storage while preserving all historical data, since each
        snapshot contains 14 days of daily breakdown from GitHub. As long as
        we snapshot at least once per day, no data is lost.

        Returns:
            Number of rows deleted
        """
        from database import get_db

        with get_db() as conn:
            # Delete all snapshots except the most recent per day
            # We keep the row with the MAX(timestamp) for each date
            cursor = conn.execute("""
                DELETE FROM github_metrics
                WHERE daemon_id = ? AND id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY date ORDER BY timestamp DESC
                        ) as rn
                        FROM github_metrics
                        WHERE daemon_id = ?
                    ) WHERE rn = 1
                )
            """, (self._daemon_id, self._daemon_id))
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} duplicate GitHub metrics snapshots")

        return deleted

    async def refresh_metrics(self) -> MetricsSnapshot:
        """Fetch and save fresh metrics, then cleanup duplicates."""
        snapshot = await self.fetch_all_metrics()
        self.save_snapshot(snapshot)
        self.cleanup_duplicate_snapshots()
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
        days: Optional[int] = 30,
        repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical metrics for the specified number of days.

        Args:
            days: Number of days of history to retrieve. None or 0 = all time.
            repo: Optional specific repo to filter for

        Returns:
            List of snapshots, oldest first (one per day, latest snapshot of each day)
        """
        from database import get_db, json_deserialize

        # None or 0 means all time
        if days is None or days == 0:
            cutoff_date = "1970-01-01"
        else:
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
        days: Optional[int] = 14,
        repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get time series data for a specific metric.

        Args:
            metric: One of 'clones', 'clones_uniques', 'views', 'views_uniques', 'stars', 'forks'
            days: Number of days. None or 0 = all time.
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

    def get_all_time_repo_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all-time aggregate statistics per repository.

        Strategy: Start with the current 14-day totals from GitHub (which are
        authoritative), then add any historical daily data from dates that have
        rolled out of the current 14-day window.

        Stars, forks, watchers, and issues are point-in-time values from the
        most recent snapshot.

        Returns:
            Dict mapping repo names to their all-time stats
        """
        from database import get_db, json_deserialize

        # Get current snapshot as baseline (authoritative 14-day totals)
        current = self.get_current_metrics()
        if not current:
            return {}

        # Calculate the cutoff date - dates before this have rolled out of
        # GitHub's current 14-day window and need to be added from history
        cutoff_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

        # Initialize results with current 14-day totals
        result: Dict[str, Dict[str, Any]] = {}
        for repo_name, repo_data in (current.get("repos", {}) or {}).items():
            result[repo_name] = {
                "repo": repo_name,
                "clones_count": repo_data.get("clones_count", 0),
                "clones_uniques": repo_data.get("clones_uniques", 0),
                "views_count": repo_data.get("views_count", 0),
                "views_uniques": repo_data.get("views_uniques", 0),
                "stars": repo_data.get("stars", 0),
                "forks": repo_data.get("forks", 0),
                "watchers": repo_data.get("watchers", 0),
                "open_issues": repo_data.get("open_issues", 0),
            }

        # Now add historical data from dates BEFORE the current 14-day window
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT date, repos_json
                FROM github_metrics
                WHERE daemon_id = ?
                ORDER BY date ASC
            """, (self._daemon_id,))

            # Track which historical dates we've already counted
            seen_dates: Dict[str, set] = {repo: set() for repo in result}

            for row in cursor.fetchall():
                repos_data = json_deserialize(row[1]) or {}

                for repo_name, repo_data in repos_data.items():
                    if repo_name not in result:
                        continue
                    if repo_name not in seen_dates:
                        seen_dates[repo_name] = set()

                    # Process daily clones data - only add dates before cutoff
                    for daily in repo_data.get("clones_daily", []):
                        daily_date = daily.get("timestamp", "")[:10]
                        if daily_date < cutoff_date and daily_date not in seen_dates[repo_name]:
                            seen_dates[repo_name].add(daily_date)
                            result[repo_name]["clones_count"] += daily.get("count", 0)
                            result[repo_name]["clones_uniques"] += daily.get("uniques", 0)

                    # Process daily views data - only add dates before cutoff
                    for daily in repo_data.get("views_daily", []):
                        daily_date = daily.get("timestamp", "")[:10]
                        # Use different key to track views vs clones separately
                        views_key = f"v_{daily_date}"
                        if daily_date < cutoff_date and views_key not in seen_dates[repo_name]:
                            seen_dates[repo_name].add(views_key)
                            result[repo_name]["views_count"] += daily.get("count", 0)
                            result[repo_name]["views_uniques"] += daily.get("uniques", 0)

        return result

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
