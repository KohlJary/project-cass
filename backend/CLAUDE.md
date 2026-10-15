# Backend Notes

Claude Code loads the repository root `CLAUDE.md` along with this file, so project context, goals and workflow live there. This file used to be a full copy of that context; it drifted out of sync and kept old claims alive, so it now holds only backend-specific pointers.

- Entry point: `main_sdk.py`
- Module structure and patterns: `ARCHITECTURE.md`
- In-progress work and known issues: `TODO.md`
- Schema changes: update CREATE TABLE in `database/schema.py`, add a migration in `_apply_schema_updates()` in `database/migrations.py`, bump `SCHEMA_VERSION`
- Data lives under `DATA_DIR` (default `backend/data`); vector store at `DATA_DIR/chroma`
- Tests: `tests/`
