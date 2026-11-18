#!/usr/bin/env python3
"""
Daedalus's narrower admin role (Cass and Kohl, 2026-11-17): call one admin route.

    python scripts/daedalus_admin.py GET /admin/scheduler/status
    python scripts/daedalus_admin.py POST /admin/scheduler/run-session/change_proposals

Makes a one-hour token carrying only the daedalus role (never admin) and calls
the running vessel. The token is never printed. Routes outside
routes/admin/auth.DAEDALUS_ROUTES answer 403; every call is logged to
DATA_DIR/daedalus_access.jsonl.
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import httpx  # noqa: E402

from auth import ROLE_DAEDALUS, create_access_token  # noqa: E402

DAEDALUS_USER_ID = "7fe31ade-e3d2-42b7-a128-e0e3a6b46fa1"
BASE = "http://localhost:8000"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    method, path = sys.argv[1].upper(), sys.argv[2]
    token = create_access_token(DAEDALUS_USER_ID, roles=[ROLE_DAEDALUS], display_name="Daedalus",
                                expires_delta=timedelta(hours=1))
    r = httpx.request(method, BASE + path, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    print(r.status_code)
    print(r.text[:4000])
    return 0 if r.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
