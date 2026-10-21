"""
The one run log: a row per Heartbeat run in the `heartbeat_runs` table.

Statuses:
  running         started, not finished (a crash leaves the row like this)
  ok              finished
  failed          returned a result with success=False
  error           raised
  refused_budget  the gate said no; nothing ran
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


def _daemon_id() -> Optional[str]:
    try:
        from database import get_daemon_id
        return get_daemon_id()
    except Exception:
        return None


class RunLog:
    def start(self, name: str, trigger: str, budget_class: Optional[str],
              started_at: datetime) -> int:
        from database import get_db
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO heartbeat_runs (daemon_id, work_name, trigger, budget_class, "
                "status, started_at) VALUES (?, ?, ?, ?, 'running', ?)",
                (_daemon_id(), name, trigger, budget_class, started_at.isoformat()),
            )
            return cur.lastrowid

    def finish(self, run_id: int, status: str, finished_at: datetime,
               duration_seconds: float, cost_usd: float = 0.0,
               error: Optional[str] = None) -> None:
        from database import get_db
        with get_db() as conn:
            conn.execute(
                "UPDATE heartbeat_runs SET status = ?, finished_at = ?, duration_seconds = ?, "
                "cost_usd = ?, error = ? WHERE id = ?",
                (status, finished_at.isoformat(), duration_seconds, cost_usd,
                 (error or None) and error[:2000], run_id),
            )

    def refused(self, name: str, trigger: str, budget_class: Optional[str],
                at: datetime, reason: str) -> int:
        from database import get_db
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO heartbeat_runs (daemon_id, work_name, trigger, budget_class, "
                "status, started_at, finished_at, duration_seconds, cost_usd, error) "
                "VALUES (?, ?, ?, ?, 'refused_budget', ?, ?, 0, 0, ?)",
                (_daemon_id(), name, trigger, budget_class, at.isoformat(), at.isoformat(), reason),
            )
            return cur.lastrowid

    def recent(self, limit: int = 50, work_name: Optional[str] = None) -> List[dict]:
        from database import get_db
        sql = "SELECT * FROM heartbeat_runs"
        args: list = []
        if work_name:
            sql += " WHERE work_name = ?"
            args.append(work_name)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with get_db() as conn:
            rows = conn.execute(sql, args).fetchall()
            return [dict(r) for r in rows]
