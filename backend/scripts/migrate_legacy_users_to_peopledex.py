#!/usr/bin/env python3
"""
Copy the legacy user stores into PeopleDex (epic #55).

Sources (read, never changed or deleted):
  * the user_observations table in <data-dir>/cass.db
  * <data-dir>/users/<user_id>/user_model.yaml
  * <data-dir>/users/<user_id>/relationship_model.yaml

Target: the PeopleDex tables in the same database (peopledex_entities,
peopledex_observations, peopledex_moments, peopledex_relationship_patterns,
peopledex_mutual_shaping, peopledex_relationship_meta).

Dry run is the default: the database is opened read-only, the script prints
what it would add and the row counts, and writes nothing. --apply writes, in
one transaction.

Idempotent. An item is skipped when PeopleDex already has it:
  * by id (legacy observation ids and the YAML ids of moments, shifts,
    patterns, growth observations and contradictions are kept as PeopleDex
    ids; YAML items without an id get a deterministic uuid5), or
  * by content for the same person and daemon (the Dec 2025 migration,
    scripts/migrate_usermodel_to_peopledex.py, copied some of this already
    under fresh ids, and runtime writers may have recorded the same text).
So a second --apply adds nothing.

Relationship metadata only fills fields PeopleDex doesn't have yet; it never
overwrites one.

    DATA_DIR=/path/to/copy python scripts/migrate_legacy_users_to_peopledex.py
    DATA_DIR=/path/to/copy python scripts/migrate_legacy_users_to_peopledex.py --apply
    python scripts/migrate_legacy_users_to_peopledex.py --data-dir /path/to/copy
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

observation_type_for_category = None  # imported in main(), after DATA_DIR is set

ID_NAMESPACE = uuid.UUID("5f1d7a52-55c0-4e1b-9d55-7065706c6564")  # "peopledex" migration

PDX_TABLES = [
    "peopledex_entities",
    "peopledex_observations",
    "peopledex_moments",
    "peopledex_relationship_patterns",
    "peopledex_mutual_shaping",
    "peopledex_relationship_meta",
]
META_FIELDS = ["relationship_type", "formation_date", "current_phase",
               "first_interaction", "last_interaction"]


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def stable_id(*parts) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, "|".join(str(p) for p in parts)))


class Plan:
    """Rows to insert or update, built against the current PeopleDex state
    plus everything already planned (so a run never plans a duplicate)."""

    def __init__(self, conn):
        self.conn = conn
        self.now = datetime.now().isoformat()
        self.ops = []                 # (sql, params)
        self.added = Counter()        # table -> rows planned
        self.skipped = Counter()      # reason -> count
        self.by_source = Counter()    # (source, table) -> rows planned
        self.source = ""
        self.entities = {r[0]: r[1] for r in conn.execute(
            "SELECT user_id, id FROM peopledex_entities WHERE user_id IS NOT NULL")}
        self.ids = {t: {r[0] for r in conn.execute(f"SELECT id FROM {t}")}
                    for t in PDX_TABLES if t not in ("peopledex_relationship_meta",)}
        self.obs_keys = {(e, d, norm(c)) for e, d, c in conn.execute(
            "SELECT entity_id, daemon_id, content FROM peopledex_observations")}
        self.moment_keys = {(e, d, norm(c)) for e, d, c in conn.execute(
            "SELECT entity_id, daemon_id, description FROM peopledex_moments")}
        self.pattern_keys = {(e, d, t, norm(c)) for e, d, t, c in conn.execute(
            "SELECT entity_id, daemon_id, pattern_type, description FROM peopledex_relationship_patterns")}
        self.shaping_keys = {(e, d, t, norm(c)) for e, d, t, c in conn.execute(
            "SELECT entity_id, daemon_id, shaping_type, note FROM peopledex_mutual_shaping")}
        cur = conn.execute("SELECT * FROM peopledex_relationship_meta")
        cols = [c[0] for c in cur.description]
        self.meta = {(r["entity_id"], r["daemon_id"]): r for r in (dict(zip(cols, row)) for row in cur)}
        self.users = {r[0]: r[1] for r in conn.execute("SELECT id, display_name FROM users")}

    def _add(self, table, sql, params):
        self.ops.append((sql, params))
        self.added[table] += 1
        self.by_source[(self.source, table)] += 1

    # -- entities -----------------------------------------------------------
    def entity_for(self, user_id):
        if user_id in self.entities:
            return self.entities[user_id]
        name = self.users.get(user_id)
        if name is None:
            return None
        entity_id = stable_id("entity", user_id)
        self._add("peopledex_entities",
                  "INSERT INTO peopledex_entities (id, entity_type, primary_name, realm, "
                  "created_at, updated_at, user_id) VALUES (?, 'person', ?, 'meatspace', ?, ?, ?)",
                  (entity_id, name, self.now, self.now, user_id))
        self.ops.append((
            "INSERT INTO peopledex_attributes (id, entity_id, attribute_type, value, is_primary, "
            "source_type, created_at, updated_at) VALUES (?, ?, 'name', ?, 1, 'migration', ?, ?)",
            (stable_id("name", entity_id), entity_id, name, self.now, self.now)))
        self.entities[user_id] = entity_id
        return entity_id

    # -- observations -------------------------------------------------------
    def observation(self, *, obs_id, entity_id, daemon_id, obs_type, content, metadata=None,
                    confidence=0.7, source_type=None, source_conversation_id=None,
                    first_noticed=None, last_validated=None, validation_count=0,
                    status="active", resolution=None, resolved_at=None,
                    created_at=None, updated_at=None, also_matches=()):
        if not norm(content):
            self.skipped["empty"] += 1
            return
        if obs_id in self.ids["peopledex_observations"]:
            self.skipped["observation already in PeopleDex (same id)"] += 1
            return
        keys = [(entity_id, daemon_id, norm(c)) for c in (content, *also_matches)]
        if any(k in self.obs_keys for k in keys):
            self.skipped["observation already in PeopleDex (same text)"] += 1
            return
        self._add("peopledex_observations",
                  "INSERT INTO peopledex_observations (id, entity_id, daemon_id, observation_type, "
                  "content, metadata_json, confidence, source_type, source_conversation_id, "
                  "first_noticed, last_validated, validation_count, status, resolution, "
                  "resolved_at, created_at, updated_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (obs_id, entity_id, daemon_id, obs_type, content,
                   json.dumps(metadata) if metadata else None,
                   confidence if confidence is not None else 0.7, source_type,
                   source_conversation_id, first_noticed or created_at or self.now,
                   last_validated, validation_count or 0, status, resolution, resolved_at,
                   created_at or self.now, updated_at))
        self.ids["peopledex_observations"].add(obs_id)
        self.obs_keys.add(keys[0])

    def moment(self, *, moment_id, entity_id, daemon_id, description, significance, category,
               conversation_id, timestamp):
        if not norm(description):
            self.skipped["empty"] += 1
            return
        key = (entity_id, daemon_id, norm(description))
        if moment_id in self.ids["peopledex_moments"] or key in self.moment_keys:
            self.skipped["moment already in PeopleDex"] += 1
            return
        self._add("peopledex_moments",
                  "INSERT INTO peopledex_moments (id, entity_id, daemon_id, description, significance, "
                  "category, conversation_id, timestamp, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (moment_id, entity_id, daemon_id, description, significance,
                   category or "connection", conversation_id, timestamp or self.now, self.now))
        self.ids["peopledex_moments"].add(moment_id)
        self.moment_keys.add(key)

    def pattern(self, *, pattern_id, entity_id, daemon_id, pattern_type, description, name=None,
                frequency=None, valence=None, examples=None, from_state=None, to_state=None,
                catalyst=None, first_noticed=None, timestamp=None):
        if not norm(description):
            self.skipped["empty"] += 1
            return
        key = (entity_id, daemon_id, pattern_type, norm(description))
        if pattern_id in self.ids["peopledex_relationship_patterns"] or key in self.pattern_keys:
            self.skipped["pattern already in PeopleDex"] += 1
            return
        self._add("peopledex_relationship_patterns",
                  "INSERT INTO peopledex_relationship_patterns (id, entity_id, daemon_id, pattern_type, "
                  "name, description, frequency, valence, examples_json, from_state, to_state, "
                  "catalyst, first_noticed, timestamp, created_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (pattern_id, entity_id, daemon_id, pattern_type, name, description, frequency,
                   valence, json.dumps(examples) if examples else None, from_state, to_state,
                   catalyst or None, first_noticed, timestamp or first_noticed or self.now, self.now))
        self.ids["peopledex_relationship_patterns"].add(pattern_id)
        self.pattern_keys.add(key)

    def shaping(self, *, entity_id, daemon_id, shaping_type, note):
        if not norm(note):
            self.skipped["empty"] += 1
            return
        key = (entity_id, daemon_id, shaping_type, norm(note))
        shaping_id = stable_id("shaping", entity_id, daemon_id, shaping_type, norm(note))
        if shaping_id in self.ids["peopledex_mutual_shaping"] or key in self.shaping_keys:
            self.skipped["shaping note already in PeopleDex"] += 1
            return
        self._add("peopledex_mutual_shaping",
                  "INSERT INTO peopledex_mutual_shaping (id, entity_id, daemon_id, shaping_type, note, "
                  "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (shaping_id, entity_id, daemon_id, shaping_type, note, self.now))
        self.ids["peopledex_mutual_shaping"].add(shaping_id)
        self.shaping_keys.add(key)

    def meta_fill(self, *, entity_id, daemon_id, values, is_foundational):
        values = {k: v for k, v in values.items() if v}
        current = self.meta.get((entity_id, daemon_id))
        if current is None:
            if not values and not is_foundational:
                return
            self._add("peopledex_relationship_meta",
                      "INSERT INTO peopledex_relationship_meta (entity_id, daemon_id, relationship_type, "
                      "formation_date, current_phase, is_foundational, first_interaction, "
                      "last_interaction, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (entity_id, daemon_id, *(values.get(f) for f in META_FIELDS[:3]),
                       1 if is_foundational else 0,
                       *(values.get(f) for f in META_FIELDS[3:]), self.now))
            self.meta[(entity_id, daemon_id)] = {**values, "is_foundational": int(bool(is_foundational))}
            return
        fills = {k: v for k, v in values.items() if not current.get(k)}
        if is_foundational and not current.get("is_foundational"):
            fills["is_foundational"] = 1
        if not fills:
            self.skipped["relationship meta already filled"] += 1
            return
        sets = ", ".join(f"{k} = ?" for k in fills)
        self.ops.append((f"UPDATE peopledex_relationship_meta SET {sets}, updated_at = ? "
                         "WHERE entity_id = ? AND daemon_id = ?",
                         (*fills.values(), self.now, entity_id, daemon_id)))
        self.added["peopledex_relationship_meta (fields filled)"] += 1
        current.update(fills)


def plan_legacy_rows(plan: Plan):
    plan.source = "user_observations table"
    cur = plan.conn.execute(
        "SELECT id, daemon_id, user_id, observation_type, content_json, confidence, "
        "created_at, updated_at FROM user_observations ORDER BY created_at")
    for obs_id, daemon_id, user_id, category, content_json, confidence, created, updated in cur.fetchall():
        entity_id = plan.entity_for(user_id)
        if entity_id is None:
            plan.skipped["legacy row for a user that no longer exists"] += 1
            continue
        try:
            content = json.loads(content_json) if content_json else {}
        except (TypeError, ValueError):
            content = {"observation": content_json}
        if not isinstance(content, dict):
            content = {"observation": str(content)}
        text = content.get("observation") or content.get("content") or ""
        metadata = {k: v for k, v in content.items() if k not in ("observation", "content") and v is not None}
        metadata.update({"category": category, "migrated_from": "user_observations"})
        plan.observation(
            obs_id=obs_id, entity_id=entity_id, daemon_id=daemon_id,
            obs_type=observation_type_for_category(category), content=text, metadata=metadata,
            confidence=confidence, source_type=content.get("source_type"),
            source_conversation_id=content.get("source_conversation_id"),
            last_validated=content.get("last_validated"),
            validation_count=content.get("validation_count") or 0,
            created_at=created, updated_at=updated,
        )


def plan_yaml_models(plan: Plan, users_dir: Path, daemon_id: str, files_seen: Counter):
    plan.source = "YAML models"
    for user_id in sorted(plan.users):
        user_dir = users_dir / user_id
        um = rm = {}
        if (user_dir / "user_model.yaml").exists():
            um = yaml.safe_load((user_dir / "user_model.yaml").read_text()) or {}
            files_seen["user_model.yaml"] += 1
        if (user_dir / "relationship_model.yaml").exists():
            rm = yaml.safe_load((user_dir / "relationship_model.yaml").read_text()) or {}
            files_seen["relationship_model.yaml"] += 1
        if not um and not rm:
            continue
        entity_id = plan.entity_for(user_id)
        if entity_id is None:
            continue
        e, d = entity_id, daemon_id
        mark = {"migrated_from": "user_model.yaml"}

        for s in um.get("identity_statements") or []:
            plan.observation(
                obs_id=stable_id("identity", e, d, norm(s.get("statement"))), entity_id=e, daemon_id=d,
                obs_type="identity_statement", content=s.get("statement", ""),
                metadata={**mark, "source": s.get("source"), "evidence": s.get("evidence") or [],
                          "last_affirmed": s.get("last_affirmed")},
                confidence=s.get("confidence", 0.7), source_type=s.get("source"),
                first_noticed=s.get("first_noticed"), created_at=s.get("first_noticed"))
        for v in um.get("values") or []:
            plan.observation(obs_id=stable_id("value", e, d, norm(v)), entity_id=e, daemon_id=d,
                             obs_type="value", content=v, metadata=mark, confidence=0.9)
        cs = um.get("communication_style") or {}
        if norm(cs.get("style")):
            plan.observation(
                obs_id=stable_id("communication_style", e, d, norm(cs.get("style"))),
                entity_id=e, daemon_id=d, obs_type="communication_style", content=cs["style"],
                metadata={**mark, "preferences": cs.get("preferences") or [],
                          "patterns": cs.get("patterns") or {},
                          "effective_approaches": cs.get("effective_approaches") or [],
                          "avoid": cs.get("avoid") or []},
                confidence=0.9)
        for g in um.get("growth_observations") or []:
            plan.observation(
                obs_id=g.get("id") or stable_id("growth", e, d, norm(g.get("observation"))),
                entity_id=e, daemon_id=d, obs_type="growth_observation", content=g.get("observation", ""),
                metadata={**mark, "area": g.get("area"), "direction": g.get("direction"),
                          "evidence": g.get("evidence")},
                first_noticed=g.get("timestamp"), created_at=g.get("timestamp"))
        for g in um.get("growth_edges") or []:
            plan.observation(
                obs_id=stable_id("growth_edge", e, d, norm(g.get("area")), norm(g.get("current_state"))),
                entity_id=e, daemon_id=d, obs_type="growth_observation",
                content=g.get("current_state", ""),
                metadata={**mark, "area": g.get("area"), "kind": "growth_edge",
                          "observations": g.get("observations") or []},
                first_noticed=g.get("first_noticed"), created_at=g.get("first_noticed"))
        for q in um.get("open_questions") or []:
            plan.observation(obs_id=stable_id("open_question", e, d, norm(q)), entity_id=e, daemon_id=d,
                             obs_type="open_question", content=q, metadata=mark)
        for c in um.get("contradictions") or []:
            a, b = c.get("aspect_a", ""), c.get("aspect_b", "")
            plan.observation(
                obs_id=c.get("id") or stable_id("contradiction", e, d, norm(a), norm(b)),
                entity_id=e, daemon_id=d, obs_type="contradiction", content=f"{a} vs {b}",
                also_matches=(f"{a} ↔ {b}",),
                metadata={**mark, "aspect_a": a, "aspect_b": b, "context": c.get("context")},
                status="resolved" if c.get("resolved") else "active",
                resolution=c.get("resolution"), resolved_at=c.get("resolution_timestamp"),
                first_noticed=c.get("timestamp"), created_at=c.get("timestamp"))
        for q in um.get("relationship_qualities") or []:
            plan.observation(obs_id=stable_id("relationship_quality", e, d, norm(q)), entity_id=e,
                             daemon_id=d, obs_type="general", content=q,
                             metadata={**mark, "category": "relationship_quality"})
        for m in um.get("shared_history") or []:
            plan.moment(moment_id=m.get("id") or stable_id("moment", e, d, norm(m.get("description"))),
                        entity_id=e, daemon_id=d, description=m.get("description", ""),
                        significance=m.get("significance"), category=m.get("category"),
                        conversation_id=m.get("conversation_id"), timestamp=m.get("timestamp"))

        for p in rm.get("patterns") or []:
            plan.pattern(pattern_id=p.get("id") or stable_id("pattern", e, d, norm(p.get("description"))),
                         entity_id=e, daemon_id=d, pattern_type="pattern",
                         description=p.get("description", ""), name=p.get("name"),
                         frequency=p.get("frequency"), valence=p.get("valence"),
                         examples=p.get("examples"), first_noticed=p.get("first_noticed"))
        for s in rm.get("significant_shifts") or []:
            plan.pattern(pattern_id=s.get("id") or stable_id("shift", e, d, norm(s.get("description"))),
                         entity_id=e, daemon_id=d, pattern_type="shift",
                         description=s.get("description", ""), from_state=s.get("from_state"),
                         to_state=s.get("to_state"), catalyst=s.get("catalyst"),
                         timestamp=s.get("timestamp"))
        for r in rm.get("rituals") or []:
            plan.pattern(pattern_id=stable_id("ritual", e, d, norm(r)), entity_id=e, daemon_id=d,
                         pattern_type="ritual", description=r)
        for g in rm.get("growth_areas") or []:
            plan.observation(obs_id=stable_id("relationship_growth_area", e, d, norm(g)), entity_id=e,
                             daemon_id=d, obs_type="general", content=g,
                             metadata={"migrated_from": "relationship_model.yaml",
                                       "category": "relationship_growth_area"})
        for kind, field in (("they_shape_me", "how_they_shape_me"), ("i_shape_them", "how_i_shape_them"),
                            ("inherited_value", "inherited_values")):
            for note in rm.get(field) or []:
                plan.shaping(entity_id=e, daemon_id=d, shaping_type=kind, note=note)

        plan.meta_fill(entity_id=e, daemon_id=d, values={
            "relationship_type": um.get("relationship_type"),
            "formation_date": rm.get("formation_date"),
            "current_phase": rm.get("current_phase"),
            "first_interaction": um.get("first_interaction"),
            "last_interaction": um.get("last_interaction"),
        }, is_foundational=bool(rm.get("is_foundational")))


def counts(conn):
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ["user_observations", *PDX_TABLES]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR"),
                        help="data directory holding cass.db and users/ (default: $DATA_DIR)")
    parser.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    parser.add_argument("--daemon-id", help="daemon the YAML models belong to (default: the 'cass' daemon)")
    args = parser.parse_args(argv)
    if not args.data_dir:
        parser.error("set --data-dir or DATA_DIR")

    data_dir = Path(args.data_dir).expanduser().resolve()
    db_path = data_dir / "cass.db"
    if not db_path.is_file():
        parser.error(f"{db_path} not found")

    # The runtime's category -> observation_type mapping. Importing peopledex
    # loads config, which reads DATA_DIR; point it at the same directory so
    # nothing else is ever touched. This script opens only db_path itself.
    os.environ["DATA_DIR"] = str(data_dir)
    global observation_type_for_category
    from peopledex import observation_type_for_category

    if args.apply:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    daemon_id = args.daemon_id
    if not daemon_id:
        row = conn.execute("SELECT id FROM daemons WHERE label = 'cass' LIMIT 1").fetchone()
        if not row:
            parser.error("no 'cass' daemon in the database; pass --daemon-id")
        daemon_id = row[0]

    before = counts(conn)
    plan = Plan(conn)
    files_seen = Counter()
    plan_legacy_rows(plan)
    plan_yaml_models(plan, data_dir / "users", daemon_id, files_seen)

    mode = "APPLY" if args.apply else "DRY RUN (nothing written)"
    print(f"PeopleDex migration - {mode}")
    print(f"  database: {db_path}")
    print(f"  YAML daemon: {daemon_id}")
    print(f"  YAML files read: {dict(files_seen) or 'none'}")
    print("  to add:")
    for table, n in sorted(plan.added.items()):
        print(f"    {table}: {n}")
    if not plan.added:
        print("    nothing")
    for (source, table), n in sorted(plan.by_source.items()):
        print(f"      from {source} -> {table}: {n}")
    print("  skipped:")
    for reason, n in sorted(plan.skipped.items()):
        print(f"    {reason}: {n}")

    if args.apply and plan.ops:
        with conn:
            for sql, params in plan.ops:
                conn.execute(sql, params)
    after = counts(conn) if args.apply else None

    print("\n  table                              before    after")
    for t in before:
        projected = before[t] + plan.added.get(t, 0)
        shown = after[t] if after else projected
        label = "" if after else " (projected)"
        print(f"  {t:<34}{before[t]:>7}  {shown:>7}{label}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
