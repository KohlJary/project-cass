# Daemon Seed Exports

This directory contains portable daemon exports that can be imported into new instances.

## File Format

Daemon exports use the `.anima` extension (Latin for soul/spirit), representing the complete essence of a daemon. Internally, `.anima` files are ZIP archives containing JSON data and wiki markdown files.

## Files

- `cass_export_20251215.anima` - Full export of Cass daemon as "cass-prime" (3562 rows)
  - 65 conversations, 2509 messages
  - 300 self_observations, 28 milestones
  - 22 solo_reflections, 10 journals, 5 dreams
  - 1 identity snippet (auto-generated ~420 token identity narrative)
  - 1 project, 42 project documents
  - 264 roadmap items, 164 roadmap links
  - Research sessions, rhythm records, github metrics, etc.

## Usage

### Import a daemon

```bash
cd backend
source venv/bin/activate

# Import with default name from export (cass-prime)
python daemon_export.py import ../seed/cass_export_20251215.anima

# Or specify a custom name
python daemon_export.py import ../seed/cass_export_20251215.anima my-daemon-name
```

### Export a daemon

```bash
python daemon_export.py export <daemon_id> ../seed/cass_export_<date>.anima
```

### Preview before importing

```bash
python daemon_export.py preview ../seed/cass_export_20251215.anima
```

### List available seed exports

```bash
python daemon_export.py seeds
```

## Notes

- Exports include all SQLite data but NOT ChromaDB embeddings
- On import, embeddings are regenerated from the source data
- Use `--skip-embeddings` flag to skip embedding regeneration (faster, but search won't work)
- Projects are shared across daemons (no daemon_id) - they're included in exports
- Imports generate new IDs for all records - safe to import alongside existing daemons
- Both `.anima` and `.zip` extensions are supported for compatibility
