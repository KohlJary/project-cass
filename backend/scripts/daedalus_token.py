#!/usr/bin/env python3
"""
Print a fresh one-hour token carrying only the daedalus role (never admin),
signed by this vessel. For read-only house tools that need one per run,
e.g. Chapter-House spend-watch's `token_command`:

    {"http": "http://127.0.0.1:8000",
     "token_command": "cd ~/cass/cass-vessel/backend && venv/bin/python scripts/daedalus_token.py"}

Nothing long-lived is written anywhere. Routes outside
routes/admin/auth.DAEDALUS_ROUTES still answer 403.
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from auth import ROLE_DAEDALUS, create_access_token  # noqa: E402
from scripts.daedalus_admin import DAEDALUS_USER_ID  # noqa: E402

print(create_access_token(DAEDALUS_USER_ID, roles=[ROLE_DAEDALUS], display_name="Daedalus",
                          expires_delta=timedelta(hours=1)))
