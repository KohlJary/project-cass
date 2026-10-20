# Trial: PR #77 one backup system (e00d78e)

Verdict: the core claim is SHOWN with scope limits. Tests: 16 passed (test_data_backup, test_export_backup). Unit renders and `systemd-analyze --user verify` exits 0 on a temp copy.

Findings (ranked)
1. backend/data_backup.py:92,107 + backend/scripts/backup.py:39-42. SIGTERM mid-write (systemd stop, shutdown, timeout) leaves cass-*.zip.partial; `except BaseException` does not run on default SIGTERM. Reproduced: kill -TERM at 1.2s, rc=143, 66 MB .partial left. DAILY_NAME never matches .partial, so prune never removes it. Each leaked partial is up to ~1.8 GB, forever.
2. backend/data_backup.py:43 follow-links walk. A symlink inside DATA_DIR that points at/over the out dir defeats the refusal (it checks only the out path). Reproduced: real/escape -> ../outs; second run's zip contained the first zip (2 files vs 1). Unbounded growth only if such a link exists; currently none known.
3. backend/scripts/backup.py:20,35 + config.py:19. Importing config does DATA_DIR.mkdir(parents=True). If DATA_DIR is on an unmounted/renamed path, the script creates an empty dir and writes a valid "successful" empty backup; it then counts toward retention and ages out real ones after 7 backup-days. No minimum-size or emptiness check.
4. backend/data_backup.py:146-148 + scripts/backup.py:28-29. --keep-daily 0 --keep-weekly 0 (accepted, no validation) deletes every backup including the one just written (reproduced: kd0 -> []). Negative values untested.
5. backend/data_backup.py:113,141,147. Regex accepts impossible dates (cass-2020-13-45-0430.zip): strptime raises ValueError once the file falls outside the daily window, after the new backup is written, so the unit fails every day and pruning stops. A directory named like a backup raises IsADirectoryError (reproduced). Both need hand-made files; low likelihood.
6. Retention semantics (data_backup.py:132-145). "Last 7 days" is the 7 newest days that have a backup, not calendar days: after a gap, old backups stay as "daily" indefinitely (stale test: 12 backups from June kept 9). The first weekly keeper is usually in the same ISO week as the oldest daily, so history is 3 extra distinct weeks, not 4 (test asserts 4 distinct weeks only among the weekly files, not distinct from the daily window). Year boundary, multiple-per-day, similar names (.bak, .partial, 5-digit time, capital C) all behaved correctly.
7. Failure reporting. A failed run exits non-zero and leaves the unit failed, but nothing notifies; with Persistent=true and no OnFailure the only signal is `systemctl --user` status. Disk full: OSError propagates, partial unlinked, prune not run (correct), same silence.
8. Snapshots go through tempfile (data_backup.py:97) -> /tmp, which is tmpfs here (32G, 13G used). Largest DB is held in RAM during the copy; unchecked against actual DB sizes (did not read data).
9. Small text: scripts/backup.py:3-4 says units are in "scripts/systemd/"; they are backend/cass-backup.*. Dashboard says "4:30 AM" but the timer has RandomizedDelaySec=600.

Checked and fine
- Refusal check with symlinks: DATA_DIR and --out are both .resolve()d; --out under the link path, via the real path, equal to data dir, all refused; sibling with a common prefix (real2) allowed; --out outside allowed. On this machine backend/data -> ../data resolves to cass-vessel/data, so ~/cass/backups is outside.
- Unit: sed substitution yields a valid unit; Nice/IOSchedulingClass=idle valid in user units; timer pairs by name. config loads backend/.env from its own directory, independent of WorkingDirectory. Missing-venv not tested.
- Failure midway in-process: partial removed, prune skipped, exit non-zero.

Open tests (cheapest): SIGTERM handler or a startup sweep of stale *.zip.partial; skip symlinks resolving to out_dir in _data_files; fail if DATA_DIR did not exist before; validate keep >= 1 (daily).
Not run: real data, real timer, mid-write disk-full on a real full filesystem.
