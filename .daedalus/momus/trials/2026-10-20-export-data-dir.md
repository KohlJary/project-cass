# Trial: 73f0af3 (fix/export-data-dir) closes #16, #17, #18

Verdict by sub-claim:
1. #16 routes read config.DATA_DIR: shown (grep: no stale *_DIR constants; test passes).
2. #17 backup includes every sqlite db + chroma and restores: consistent. Document read of restored chroma works; no vector query, no live writer, no rollback-mode contention tested. Rival: locks writers in rollback-journal mode (demonstrated synthetically, 293MB db, writer got "database is locked").
3. #18 round trip: consistent, not shown. Only passes with include_users=True and a clean target; the app's two callers (daemon_export.py:1839, routes/admin/daemons.py:219) use include_users=False.

Findings (probe tests in session scratchpad, not in repo):
H1 daemon_export.py _import_shared_table: INSERT OR IGNORE hits UNIQUE(user_id) on peopledex_entities when target already has an entity for that user under another id; entity ignored, all child rows (observations, moments, rel_meta, facts) then fail FK and are dropped with only a log warning. Observed: entities 1 (existing), observations/moments/meta/facts 0.
H2 default include_users=False: users absent in target, conversations fail FK, so threads/questions (user_id FK, first_conversation_id FK) also all dropped. Observed counts 0.
M1 _import_shared_table rewrites daemon_id to target for peopledex_facts, so another daemon's facts are exported and re-attributed to the importing daemon; all users' entities exported in every daemon export (privacy scope).
M2 backup in rollback-journal mode (no journal_mode set in repo): single-step backup holds a read lock; writer blocked.
M3 Chroma sqlite snapshot vs copied segment files: comment says Chroma rebuilds; untested.
L1 .partial left behind on failure; same-second concurrent POSTs share one .partial; symlinked directories silently omitted (file symlinks followed); snapshot copy goes to tempfile.TemporaryDirectory() (/tmp, maybe tmpfs).
L2 thread_conversation_links not exported; per-user journals / other Chroma-only collections not exported.
