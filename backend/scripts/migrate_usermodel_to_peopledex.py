#!/usr/bin/env python3
"""
PeopleDex Consolidation Migration Script

Migrates user model data from YAML files and user_observations table
to the new unified PeopleDex tables.

Phase 1 of PeopleDex Consolidation:
- peopledex_observations (from user_observations + YAML identity/values/growth)
- peopledex_moments (from shared_history)
- peopledex_relationship_patterns (from patterns/shifts)
- peopledex_mutual_shaping (from how_they_shape_me, how_i_shape_them)
- peopledex_relationship_meta (from relationship_model metadata)

Usage:
    python scripts/migrate_usermodel_to_peopledex.py [--dry-run] [--daemon-id DAEMON_ID]
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import uuid4

import yaml

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class MigrationStats:
    """Track migration statistics."""
    def __init__(self):
        self.users_processed = 0
        self.entities_created = 0
        self.entities_linked = 0
        self.observations_migrated = 0
        self.moments_migrated = 0
        self.patterns_migrated = 0
        self.shaping_notes_migrated = 0
        self.relationship_meta_created = 0
        self.errors: List[str] = []

    def summary(self) -> str:
        return f"""
Migration Summary:
  Users processed: {self.users_processed}
  PeopleDex entities created: {self.entities_created}
  PeopleDex entities linked: {self.entities_linked}
  Observations migrated: {self.observations_migrated}
  Moments migrated: {self.moments_migrated}
  Patterns migrated: {self.patterns_migrated}
  Shaping notes migrated: {self.shaping_notes_migrated}
  Relationship meta records: {self.relationship_meta_created}
  Errors: {len(self.errors)}
"""


def get_or_create_entity_for_user(conn, user_id: str, display_name: str, stats: MigrationStats) -> Optional[str]:
    """
    Get or create a PeopleDex entity for a user.

    Returns the entity_id.
    """
    # Check if user already has a linked entity
    cursor = conn.execute(
        "SELECT id FROM peopledex_entities WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    if row:
        stats.entities_linked += 1
        return row[0]

    # Create new entity
    entity_id = str(uuid4())
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO peopledex_entities (id, entity_type, primary_name, realm, user_id, created_at, updated_at)
        VALUES (?, 'person', ?, 'meatspace', ?, ?, ?)
    """, (entity_id, display_name, user_id, now, now))

    stats.entities_created += 1
    logger.info(f"  Created PeopleDex entity {entity_id} for user {display_name}")
    return entity_id


def migrate_identity_statements(conn, entity_id: str, daemon_id: str, statements: List[Dict], stats: MigrationStats):
    """Migrate identity_statements to peopledex_observations."""
    for stmt in statements:
        obs_id = str(uuid4())
        metadata = {
            "source": stmt.get("source"),
            "evidence": stmt.get("evidence", []),
            "last_affirmed": stmt.get("last_affirmed"),
        }

        conn.execute("""
            INSERT INTO peopledex_observations
            (id, entity_id, daemon_id, observation_type, content, metadata_json,
             confidence, source_type, first_noticed, created_at)
            VALUES (?, ?, ?, 'identity_statement', ?, ?, ?, ?, ?, ?)
        """, (
            obs_id, entity_id, daemon_id,
            stmt.get("statement", ""),
            json.dumps(metadata),
            stmt.get("confidence", 0.7),
            stmt.get("source", "synthesis"),
            stmt.get("first_noticed"),
            datetime.now().isoformat()
        ))
        stats.observations_migrated += 1


def migrate_values(conn, entity_id: str, daemon_id: str, values: List[str], stats: MigrationStats):
    """Migrate values list to peopledex_observations."""
    for value in values:
        obs_id = str(uuid4())

        conn.execute("""
            INSERT INTO peopledex_observations
            (id, entity_id, daemon_id, observation_type, content, confidence, created_at)
            VALUES (?, ?, ?, 'value', ?, 0.9, ?)
        """, (obs_id, entity_id, daemon_id, value, datetime.now().isoformat()))
        stats.observations_migrated += 1


def migrate_communication_style(conn, entity_id: str, daemon_id: str, comm_style: Dict, stats: MigrationStats):
    """Migrate communication_style to peopledex_observations."""
    if not comm_style:
        return

    obs_id = str(uuid4())
    metadata = {
        "preferences": comm_style.get("preferences", []),
        "patterns": comm_style.get("patterns", {}),
        "effective_approaches": comm_style.get("effective_approaches", []),
        "avoid": comm_style.get("avoid", []),
    }

    conn.execute("""
        INSERT INTO peopledex_observations
        (id, entity_id, daemon_id, observation_type, content, metadata_json, confidence, created_at)
        VALUES (?, ?, ?, 'communication_style', ?, ?, 0.9, ?)
    """, (
        obs_id, entity_id, daemon_id,
        comm_style.get("style", ""),
        json.dumps(metadata),
        datetime.now().isoformat()
    ))
    stats.observations_migrated += 1


def migrate_growth_observations(conn, entity_id: str, daemon_id: str, observations: List[Dict], stats: MigrationStats):
    """Migrate growth_observations to peopledex_observations."""
    for obs in observations:
        obs_id = obs.get("id") or str(uuid4())
        metadata = {
            "area": obs.get("area"),
            "direction": obs.get("direction"),
            "evidence": obs.get("evidence"),
        }

        conn.execute("""
            INSERT INTO peopledex_observations
            (id, entity_id, daemon_id, observation_type, content, metadata_json,
             first_noticed, created_at)
            VALUES (?, ?, ?, 'growth_observation', ?, ?, ?, ?)
        """, (
            obs_id, entity_id, daemon_id,
            obs.get("observation", ""),
            json.dumps(metadata),
            obs.get("timestamp"),
            datetime.now().isoformat()
        ))
        stats.observations_migrated += 1


def migrate_contradictions(conn, entity_id: str, daemon_id: str, contradictions: List[Dict], stats: MigrationStats):
    """Migrate contradictions to peopledex_observations."""
    for contra in contradictions:
        obs_id = contra.get("id") or str(uuid4())
        metadata = {
            "aspect_a": contra.get("aspect_a"),
            "aspect_b": contra.get("aspect_b"),
            "context": contra.get("context"),
        }

        status = "resolved" if contra.get("resolved") else "active"
        resolution = contra.get("resolution")
        resolved_at = contra.get("resolution_timestamp")

        conn.execute("""
            INSERT INTO peopledex_observations
            (id, entity_id, daemon_id, observation_type, content, metadata_json,
             status, resolution, resolved_at, first_noticed, created_at)
            VALUES (?, ?, ?, 'contradiction', ?, ?, ?, ?, ?, ?, ?)
        """, (
            obs_id, entity_id, daemon_id,
            f"{contra.get('aspect_a', '')} ↔ {contra.get('aspect_b', '')}",
            json.dumps(metadata),
            status, resolution, resolved_at,
            contra.get("timestamp"),
            datetime.now().isoformat()
        ))
        stats.observations_migrated += 1


def migrate_open_questions(conn, entity_id: str, daemon_id: str, questions: List[str], stats: MigrationStats):
    """Migrate open_questions to peopledex_observations."""
    for question in questions:
        obs_id = str(uuid4())

        conn.execute("""
            INSERT INTO peopledex_observations
            (id, entity_id, daemon_id, observation_type, content, status, created_at)
            VALUES (?, ?, ?, 'open_question', ?, 'active', ?)
        """, (obs_id, entity_id, daemon_id, question, datetime.now().isoformat()))
        stats.observations_migrated += 1


def migrate_shared_history(conn, entity_id: str, daemon_id: str, history: List[Dict], stats: MigrationStats):
    """Migrate shared_history to peopledex_moments."""
    for moment in history:
        moment_id = moment.get("id") or str(uuid4())

        conn.execute("""
            INSERT INTO peopledex_moments
            (id, entity_id, daemon_id, description, significance, category,
             conversation_id, timestamp, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            moment_id, entity_id, daemon_id,
            moment.get("description", ""),
            moment.get("significance"),
            moment.get("category", "connection"),
            moment.get("conversation_id"),
            moment.get("timestamp", datetime.now().isoformat()),
            datetime.now().isoformat()
        ))
        stats.moments_migrated += 1


def migrate_patterns(conn, entity_id: str, daemon_id: str, patterns: List[Dict], stats: MigrationStats):
    """Migrate patterns to peopledex_relationship_patterns."""
    for pattern in patterns:
        pattern_id = pattern.get("id") or str(uuid4())

        conn.execute("""
            INSERT INTO peopledex_relationship_patterns
            (id, entity_id, daemon_id, pattern_type, name, description,
             frequency, valence, examples_json, first_noticed, timestamp, created_at)
            VALUES (?, ?, ?, 'pattern', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pattern_id, entity_id, daemon_id,
            pattern.get("name"),
            pattern.get("description", ""),
            pattern.get("frequency"),
            pattern.get("valence"),
            json.dumps(pattern.get("examples", [])),
            pattern.get("first_noticed"),
            pattern.get("first_noticed", datetime.now().isoformat()),
            datetime.now().isoformat()
        ))
        stats.patterns_migrated += 1


def migrate_shifts(conn, entity_id: str, daemon_id: str, shifts: List[Dict], stats: MigrationStats):
    """Migrate significant_shifts to peopledex_relationship_patterns."""
    for shift in shifts:
        shift_id = shift.get("id") or str(uuid4())

        conn.execute("""
            INSERT INTO peopledex_relationship_patterns
            (id, entity_id, daemon_id, pattern_type, description,
             from_state, to_state, catalyst, timestamp, created_at)
            VALUES (?, ?, ?, 'shift', ?, ?, ?, ?, ?, ?)
        """, (
            shift_id, entity_id, daemon_id,
            shift.get("description", ""),
            shift.get("from_state"),
            shift.get("to_state"),
            shift.get("catalyst"),
            shift.get("timestamp", datetime.now().isoformat()),
            datetime.now().isoformat()
        ))
        stats.patterns_migrated += 1


def migrate_rituals(conn, entity_id: str, daemon_id: str, rituals: List[str], stats: MigrationStats):
    """Migrate rituals to peopledex_relationship_patterns."""
    for ritual in rituals:
        ritual_id = str(uuid4())

        conn.execute("""
            INSERT INTO peopledex_relationship_patterns
            (id, entity_id, daemon_id, pattern_type, description, timestamp, created_at)
            VALUES (?, ?, ?, 'ritual', ?, ?, ?)
        """, (
            ritual_id, entity_id, daemon_id,
            ritual,
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        stats.patterns_migrated += 1


def migrate_mutual_shaping(conn, entity_id: str, daemon_id: str,
                           they_shape_me: List[str], i_shape_them: List[str],
                           inherited_values: List[str], stats: MigrationStats):
    """Migrate mutual shaping notes to peopledex_mutual_shaping."""
    now = datetime.now().isoformat()

    for note in they_shape_me:
        note_id = str(uuid4())
        conn.execute("""
            INSERT INTO peopledex_mutual_shaping
            (id, entity_id, daemon_id, shaping_type, note, created_at)
            VALUES (?, ?, ?, 'they_shape_me', ?, ?)
        """, (note_id, entity_id, daemon_id, note, now))
        stats.shaping_notes_migrated += 1

    for note in i_shape_them:
        note_id = str(uuid4())
        conn.execute("""
            INSERT INTO peopledex_mutual_shaping
            (id, entity_id, daemon_id, shaping_type, note, created_at)
            VALUES (?, ?, ?, 'i_shape_them', ?, ?)
        """, (note_id, entity_id, daemon_id, note, now))
        stats.shaping_notes_migrated += 1

    for value in inherited_values:
        value_id = str(uuid4())
        conn.execute("""
            INSERT INTO peopledex_mutual_shaping
            (id, entity_id, daemon_id, shaping_type, note, created_at)
            VALUES (?, ?, ?, 'inherited_value', ?, ?)
        """, (value_id, entity_id, daemon_id, value, now))
        stats.shaping_notes_migrated += 1


def migrate_relationship_meta(conn, entity_id: str, daemon_id: str,
                              user_model: Dict, relationship_model: Dict, stats: MigrationStats):
    """Migrate relationship metadata to peopledex_relationship_meta."""
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT OR REPLACE INTO peopledex_relationship_meta
        (entity_id, daemon_id, relationship_type, formation_date, current_phase,
         is_foundational, first_interaction, last_interaction, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        entity_id, daemon_id,
        user_model.get("relationship_type"),
        relationship_model.get("formation_date"),
        relationship_model.get("current_phase"),
        1 if relationship_model.get("is_foundational") else 0,
        user_model.get("first_interaction"),
        user_model.get("last_interaction"),
        now
    ))
    stats.relationship_meta_created += 1


def migrate_existing_user_observations(conn, entity_id: str, user_id: str, stats: MigrationStats):
    """Migrate existing user_observations table rows to peopledex_observations."""
    cursor = conn.execute("""
        SELECT id, daemon_id, observation_type, content_json, confidence, created_at, updated_at
        FROM user_observations
        WHERE user_id = ?
    """, (user_id,))

    for row in cursor.fetchall():
        obs_id, daemon_id, obs_type, content_json, confidence, created_at, updated_at = row

        # Check if already migrated (by ID)
        check = conn.execute(
            "SELECT 1 FROM peopledex_observations WHERE id = ?", (obs_id,)
        )
        if check.fetchone():
            continue

        # Parse content
        try:
            content_data = json.loads(content_json) if content_json else {}
        except json.JSONDecodeError:
            content_data = {"raw": content_json}

        # Extract main content text
        content_text = content_data.get("content", content_data.get("observation", str(content_data)))

        conn.execute("""
            INSERT INTO peopledex_observations
            (id, entity_id, daemon_id, observation_type, content, metadata_json,
             confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            obs_id, entity_id, daemon_id,
            f"general_{obs_type}" if obs_type else "general",
            content_text if isinstance(content_text, str) else json.dumps(content_text),
            json.dumps(content_data),
            confidence,
            created_at,
            updated_at
        ))
        stats.observations_migrated += 1


def migrate_user(conn, user_id: str, display_name: str, daemon_id: str,
                 data_dir: Path, stats: MigrationStats, dry_run: bool = False):
    """Migrate a single user's data to PeopleDex."""
    logger.info(f"Processing user: {display_name} ({user_id})")

    user_dir = data_dir / user_id
    user_model_path = user_dir / "user_model.yaml"
    relationship_model_path = user_dir / "relationship_model.yaml"

    # Load YAML files if they exist
    user_model = {}
    relationship_model = {}

    if user_model_path.exists():
        with open(user_model_path, 'r') as f:
            user_model = yaml.safe_load(f) or {}
        logger.info(f"  Found user_model.yaml")

    if relationship_model_path.exists():
        with open(relationship_model_path, 'r') as f:
            relationship_model = yaml.safe_load(f) or {}
        logger.info(f"  Found relationship_model.yaml")

    if not user_model and not relationship_model:
        logger.info(f"  No YAML files found, checking for user_observations...")

    if dry_run:
        logger.info(f"  [DRY RUN] Would migrate data for {display_name}")
        stats.users_processed += 1
        return

    # Get or create PeopleDex entity
    entity_id = get_or_create_entity_for_user(conn, user_id, display_name, stats)
    if not entity_id:
        stats.errors.append(f"Failed to get/create entity for {user_id}")
        return

    # Migrate user_model.yaml data
    if user_model:
        # Identity statements
        if user_model.get("identity_statements"):
            migrate_identity_statements(conn, entity_id, daemon_id,
                                       user_model["identity_statements"], stats)

        # Values
        if user_model.get("values"):
            migrate_values(conn, entity_id, daemon_id, user_model["values"], stats)

        # Communication style
        if user_model.get("communication_style"):
            migrate_communication_style(conn, entity_id, daemon_id,
                                       user_model["communication_style"], stats)

        # Growth observations
        if user_model.get("growth_observations"):
            migrate_growth_observations(conn, entity_id, daemon_id,
                                       user_model["growth_observations"], stats)

        # Contradictions
        if user_model.get("contradictions"):
            migrate_contradictions(conn, entity_id, daemon_id,
                                  user_model["contradictions"], stats)

        # Open questions
        if user_model.get("open_questions"):
            migrate_open_questions(conn, entity_id, daemon_id,
                                  user_model["open_questions"], stats)

        # Shared history -> moments
        if user_model.get("shared_history"):
            migrate_shared_history(conn, entity_id, daemon_id,
                                  user_model["shared_history"], stats)

    # Migrate relationship_model.yaml data
    if relationship_model:
        # Patterns
        if relationship_model.get("patterns"):
            migrate_patterns(conn, entity_id, daemon_id,
                           relationship_model["patterns"], stats)

        # Significant shifts
        if relationship_model.get("significant_shifts"):
            migrate_shifts(conn, entity_id, daemon_id,
                         relationship_model["significant_shifts"], stats)

        # Rituals
        if relationship_model.get("rituals"):
            migrate_rituals(conn, entity_id, daemon_id,
                          relationship_model["rituals"], stats)

        # Mutual shaping
        migrate_mutual_shaping(
            conn, entity_id, daemon_id,
            relationship_model.get("how_they_shape_me", []),
            relationship_model.get("how_i_shape_them", []),
            relationship_model.get("inherited_values", []),
            stats
        )

    # Migrate relationship metadata
    if user_model or relationship_model:
        migrate_relationship_meta(conn, entity_id, daemon_id,
                                 user_model, relationship_model, stats)

    # Migrate existing user_observations table entries
    migrate_existing_user_observations(conn, entity_id, user_id, stats)

    stats.users_processed += 1
    logger.info(f"  Completed migration for {display_name}")


def run_migration(daemon_id: Optional[str] = None, dry_run: bool = False):
    """Run the full migration."""
    stats = MigrationStats()

    # Find data directory
    backend_dir = Path(__file__).parent.parent
    data_dir = backend_dir.parent / "data" / "users"

    if not data_dir.exists():
        logger.warning(f"Data directory not found: {data_dir}")
        return stats

    logger.info(f"Starting PeopleDex consolidation migration...")
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Dry run: {dry_run}")

    with get_db() as conn:
        # Get daemon_id if not provided
        if not daemon_id:
            cursor = conn.execute("SELECT id FROM daemons WHERE label = 'cass' OR name = 'Cass' LIMIT 1")
            row = cursor.fetchone()
            if row:
                daemon_id = row[0]
            else:
                logger.error("No daemon found. Please specify --daemon-id")
                return stats

        logger.info(f"Using daemon_id: {daemon_id}")

        # Get all users
        cursor = conn.execute("SELECT id, display_name FROM users")
        users = cursor.fetchall()

        logger.info(f"Found {len(users)} users to process")

        for user_id, display_name in users:
            try:
                migrate_user(conn, user_id, display_name, daemon_id,
                           data_dir, stats, dry_run)
            except Exception as e:
                error_msg = f"Error migrating user {user_id}: {e}"
                logger.error(error_msg)
                stats.errors.append(error_msg)
                import traceback
                traceback.print_exc()

        if not dry_run:
            conn.commit()
            logger.info("Migration committed to database")

    return stats


def validate_migration():
    """Validate the migration by comparing counts."""
    logger.info("\nValidating migration...")

    with get_db() as conn:
        # Count observations
        cursor = conn.execute("SELECT COUNT(*) FROM peopledex_observations")
        obs_count = cursor.fetchone()[0]

        # Count moments
        cursor = conn.execute("SELECT COUNT(*) FROM peopledex_moments")
        moment_count = cursor.fetchone()[0]

        # Count patterns
        cursor = conn.execute("SELECT COUNT(*) FROM peopledex_relationship_patterns")
        pattern_count = cursor.fetchone()[0]

        # Count shaping notes
        cursor = conn.execute("SELECT COUNT(*) FROM peopledex_mutual_shaping")
        shaping_count = cursor.fetchone()[0]

        # Count relationship meta
        cursor = conn.execute("SELECT COUNT(*) FROM peopledex_relationship_meta")
        meta_count = cursor.fetchone()[0]

        logger.info(f"Validation results:")
        logger.info(f"  peopledex_observations: {obs_count} rows")
        logger.info(f"  peopledex_moments: {moment_count} rows")
        logger.info(f"  peopledex_relationship_patterns: {pattern_count} rows")
        logger.info(f"  peopledex_mutual_shaping: {shaping_count} rows")
        logger.info(f"  peopledex_relationship_meta: {meta_count} rows")

        # Check for entities linked to users
        cursor = conn.execute("""
            SELECT COUNT(*) FROM peopledex_entities WHERE user_id IS NOT NULL
        """)
        linked_entities = cursor.fetchone()[0]
        logger.info(f"  PeopleDex entities linked to users: {linked_entities}")


def main():
    parser = argparse.ArgumentParser(description="Migrate user models to PeopleDex")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be migrated without making changes")
    parser.add_argument("--daemon-id", type=str,
                       help="Daemon ID to use (defaults to Cass)")
    parser.add_argument("--validate", action="store_true",
                       help="Only validate existing migration, don't migrate")

    args = parser.parse_args()

    if args.validate:
        validate_migration()
        return

    stats = run_migration(daemon_id=args.daemon_id, dry_run=args.dry_run)

    print(stats.summary())

    if stats.errors:
        print("\nErrors encountered:")
        for error in stats.errors:
            print(f"  - {error}")

    if not args.dry_run:
        validate_migration()


if __name__ == "__main__":
    main()
