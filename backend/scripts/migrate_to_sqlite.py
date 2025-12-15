#!/usr/bin/env python3
"""
Migration Script: JSON/YAML to SQLite

Migrates all data from flat file storage to the new SQLite database.
Run this once to populate the database, then switch manager classes to use SQLite.

Usage:
    cd backend
    python scripts/migrate_to_sqlite.py

This script is idempotent - it will skip records that already exist.
"""

import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import uuid

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    init_database, get_db, get_or_create_daemon,
    json_serialize, DATABASE_PATH
)
from config import DATA_DIR


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def load_json(path: Path) -> Optional[dict]:
    """Load JSON file, return None if doesn't exist or invalid."""
    try:
        if path.exists():
            with open(path, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  Warning: Could not load {path}: {e}")
    return None


def load_yaml(path: Path) -> Optional[dict]:
    """Load YAML file, return None if doesn't exist or invalid."""
    try:
        if path.exists():
            with open(path, 'r') as f:
                return yaml.safe_load(f)
    except (yaml.YAMLError, IOError) as e:
        print(f"  Warning: Could not load {path}: {e}")
    return None


def record_exists(conn, table: str, id_column: str, id_value: str) -> bool:
    """Check if a record already exists."""
    cursor = conn.execute(
        f"SELECT 1 FROM {table} WHERE {id_column} = ?",
        (id_value,)
    )
    return cursor.fetchone() is not None


# =============================================================================
# MIGRATION FUNCTIONS
# =============================================================================

def migrate_users(conn, daemon_id: str) -> dict:
    """
    Migrate users from data/users/{uuid}/ directories.
    Returns mapping of old user_id -> new user_id (same in this case).
    """
    print("\n=== Migrating Users ===")
    users_dir = DATA_DIR / "users"
    user_count = 0
    user_ids = {}

    if not users_dir.exists():
        print("  No users directory found")
        return user_ids

    # Load index to find user directories
    # Index format is {user_id: display_name}
    index_path = users_dir / "index.json"
    index = load_json(index_path) or {}

    # Get user IDs from index keys (index is {user_id: display_name})
    user_id_list = list(index.keys()) if isinstance(index, dict) else []

    for user_id in user_id_list:
        user_dir = users_dir / user_id

        if not user_dir.is_dir():
            continue

        if record_exists(conn, "users", "id", user_id):
            print(f"  User {user_id} already exists, skipping")
            user_ids[user_id] = user_id
            continue

        # Load profile
        profile = load_yaml(user_dir / "profile.yaml") or {}
        auth = load_json(user_dir / "auth.json") or {}

        # Insert user
        conn.execute("""
            INSERT INTO users (
                id, display_name, relationship, background_json,
                communication_json, preferences_json, password_hash,
                is_admin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            profile.get("display_name", "Unknown"),
            profile.get("relationship"),
            json_serialize(profile.get("background")),
            json_serialize(profile.get("communication")),
            json_serialize(profile.get("preferences")),
            auth.get("password_hash"),
            1 if profile.get("is_admin") else 0,
            profile.get("created_at", datetime.now().isoformat()),
            profile.get("updated_at", datetime.now().isoformat())
        ))

        user_ids[user_id] = user_id
        user_count += 1
        print(f"  Migrated user: {profile.get('display_name', user_id)}")

        # Migrate user observations
        observations = load_json(user_dir / "observations.json") or []
        for obs in observations:
            obs_id = obs.get("id", str(uuid.uuid4()))
            if not record_exists(conn, "user_observations", "id", obs_id):
                conn.execute("""
                    INSERT INTO user_observations (
                        id, daemon_id, user_id, observation_type,
                        content_json, confidence, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    obs_id,
                    daemon_id,
                    user_id,
                    obs.get("type", obs.get("observation_type", "general")),
                    json_serialize(obs),
                    obs.get("confidence"),
                    obs.get("created_at", obs.get("timestamp", datetime.now().isoformat())),
                    obs.get("updated_at")
                ))

    print(f"  Total users migrated: {user_count}")
    return user_ids


def migrate_conversations(conn, daemon_id: str) -> int:
    """Migrate conversations from data/conversations/*.json"""
    print("\n=== Migrating Conversations ===")
    conv_dir = DATA_DIR / "conversations"
    conv_count = 0
    msg_count = 0

    if not conv_dir.exists():
        print("  No conversations directory found")
        return 0

    for conv_file in conv_dir.glob("*.json"):
        if conv_file.name == "index.json":
            continue

        conv = load_json(conv_file)
        if not conv:
            continue

        conv_id = conv.get("id", conv_file.stem)

        if record_exists(conn, "conversations", "id", conv_id):
            print(f"  Conversation {conv_id[:8]}... already exists, skipping")
            continue

        # Insert conversation
        conn.execute("""
            INSERT INTO conversations (
                id, daemon_id, user_id, project_id, title,
                working_summary, last_summary_timestamp,
                messages_since_last_summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            conv_id,
            daemon_id,
            conv.get("user_id"),
            conv.get("project_id"),
            conv.get("title"),
            conv.get("working_summary"),
            conv.get("last_summary_timestamp"),
            conv.get("messages_since_last_summary", 0),
            conv.get("created_at", datetime.now().isoformat()),
            conv.get("updated_at", datetime.now().isoformat())
        ))

        # Insert messages
        for msg in conv.get("messages", []):
            conn.execute("""
                INSERT INTO messages (
                    conversation_id, role, content, timestamp, excluded,
                    user_id, provider, model, input_tokens, output_tokens,
                    animations_json, self_observations_json,
                    user_observations_json, marks_json, narration_metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conv_id,
                msg.get("role", "user"),
                msg.get("content", ""),
                msg.get("timestamp", datetime.now().isoformat()),
                1 if msg.get("excluded") else 0,
                msg.get("user_id"),
                msg.get("provider"),
                msg.get("model"),
                msg.get("input_tokens"),
                msg.get("output_tokens"),
                json_serialize(msg.get("animations")),
                json_serialize(msg.get("self_observations")),
                json_serialize(msg.get("user_observations")),
                json_serialize(msg.get("marks")),
                json_serialize(msg.get("narration_metrics"))
            ))
            msg_count += 1

        conv_count += 1
        title_preview = (conv.get("title") or "Untitled")[:40]
        print(f"  Migrated: {title_preview}... ({len(conv.get('messages', []))} msgs)")

    print(f"  Total: {conv_count} conversations, {msg_count} messages")
    return conv_count


def migrate_self_profile(conn, daemon_id: str):
    """Migrate Cass's self-profile from data/cass/self_profile.yaml"""
    print("\n=== Migrating Self Profile ===")

    profile_path = DATA_DIR / "cass" / "self_profile.yaml"
    profile = load_yaml(profile_path)

    if not profile:
        # Try root level
        profile_path = DATA_DIR / "self_profile.yaml"
        profile = load_yaml(profile_path)

    if not profile:
        print("  No self profile found")
        return

    if record_exists(conn, "daemon_profiles", "daemon_id", daemon_id):
        print("  Daemon profile already exists, updating...")
        conn.execute("""
            UPDATE daemon_profiles SET
                identity_statements_json = ?,
                values_json = ?,
                communication_patterns_json = ?,
                capabilities_json = ?,
                limitations_json = ?,
                open_questions_json = ?,
                notes = ?,
                updated_at = ?
            WHERE daemon_id = ?
        """, (
            json_serialize(profile.get("identity_statements")),
            json_serialize(profile.get("values")),
            json_serialize(profile.get("communication_patterns")),
            json_serialize(profile.get("capabilities")),
            json_serialize(profile.get("limitations")),
            json_serialize(profile.get("open_questions")),
            profile.get("notes"),
            profile.get("updated_at", datetime.now().isoformat()),
            daemon_id
        ))
    else:
        conn.execute("""
            INSERT INTO daemon_profiles (
                daemon_id, identity_statements_json, values_json,
                communication_patterns_json, capabilities_json,
                limitations_json, open_questions_json, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            daemon_id,
            json_serialize(profile.get("identity_statements")),
            json_serialize(profile.get("values")),
            json_serialize(profile.get("communication_patterns")),
            json_serialize(profile.get("capabilities")),
            json_serialize(profile.get("limitations")),
            json_serialize(profile.get("open_questions")),
            profile.get("notes"),
            profile.get("updated_at", datetime.now().isoformat())
        ))

    # Migrate growth edges
    for edge in profile.get("growth_edges", []):
        conn.execute("""
            INSERT INTO growth_edges (
                daemon_id, area, current_state, desired_state,
                observations_json, strategies_json, first_noticed, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            daemon_id,
            edge.get("area", "Unknown"),
            edge.get("current_state"),
            edge.get("desired_state"),
            json_serialize(edge.get("observations")),
            json_serialize(edge.get("strategies")),
            edge.get("first_noticed"),
            edge.get("last_updated")
        ))

    # Migrate opinions
    for opinion in profile.get("opinions", []):
        conn.execute("""
            INSERT INTO opinions (
                daemon_id, topic, position, confidence,
                rationale, formed_from, evolution_json,
                date_formed, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            daemon_id,
            opinion.get("topic", "Unknown"),
            opinion.get("position", ""),
            opinion.get("confidence"),
            opinion.get("rationale"),
            opinion.get("formed_from"),
            json_serialize(opinion.get("evolution")),
            opinion.get("date_formed"),
            opinion.get("last_updated")
        ))

    identity_count = len(profile.get("identity_statements", []))
    edge_count = len(profile.get("growth_edges", []))
    opinion_count = len(profile.get("opinions", []))
    print(f"  Migrated: {identity_count} identity statements, {edge_count} growth edges, {opinion_count} opinions")


def migrate_cognitive_snapshots(conn, daemon_id: str):
    """Migrate cognitive snapshots"""
    print("\n=== Migrating Cognitive Snapshots ===")

    # Try multiple locations
    for path in [
        DATA_DIR / "cass" / "cognitive_snapshots.json",
        DATA_DIR / "cognitive_snapshots.json"
    ]:
        snapshots = load_json(path)
        if snapshots and isinstance(snapshots, list) and len(snapshots) > 0:
            break
    else:
        print("  No cognitive snapshots found")
        return

    count = 0
    for snap in snapshots:
        snap_id = snap.get("id", str(uuid.uuid4()))

        if record_exists(conn, "cognitive_snapshots", "id", snap_id):
            continue

        conn.execute("""
            INSERT INTO cognitive_snapshots (
                id, daemon_id, period_start, period_end,
                metrics_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            snap_id,
            daemon_id,
            snap.get("period_start"),
            snap.get("period_end"),
            json_serialize(snap),  # Store full snapshot as metrics
            snap.get("timestamp", datetime.now().isoformat())
        ))
        count += 1

    print(f"  Migrated {count} cognitive snapshots")


def migrate_milestones(conn, daemon_id: str):
    """Migrate developmental milestones"""
    print("\n=== Migrating Milestones ===")

    for path in [
        DATA_DIR / "cass" / "developmental_milestones.json",
        DATA_DIR / "developmental_milestones.json"
    ]:
        milestones = load_json(path)
        if milestones and isinstance(milestones, list) and len(milestones) > 0:
            break
    else:
        print("  No milestones found")
        return

    count = 0
    for ms in milestones:
        ms_id = ms.get("id", str(uuid.uuid4()))

        if record_exists(conn, "milestones", "id", ms_id):
            continue

        conn.execute("""
            INSERT INTO milestones (
                id, daemon_id, title, description,
                significance, evidence_json, triggered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ms_id,
            daemon_id,
            ms.get("title", "Unknown"),
            ms.get("description"),
            ms.get("significance"),
            json_serialize(ms.get("evidence")),
            ms.get("triggered_at", ms.get("timestamp", datetime.now().isoformat()))
        ))
        count += 1

    print(f"  Migrated {count} milestones")


def migrate_self_observations(conn, daemon_id: str):
    """Migrate self observations"""
    print("\n=== Migrating Self Observations ===")

    for path in [
        DATA_DIR / "cass" / "self_observations.json",
        DATA_DIR / "self_observations.json"
    ]:
        observations = load_json(path)
        if observations and isinstance(observations, list) and len(observations) > 0:
            break
    else:
        print("  No self observations found")
        return

    count = 0
    for obs in observations:
        obs_id = obs.get("id", str(uuid.uuid4()))

        if record_exists(conn, "self_observations", "id", obs_id):
            continue

        conn.execute("""
            INSERT INTO self_observations (
                id, daemon_id, category, observation,
                confidence, context_json, source_conversation_id,
                source_journal_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            obs_id,
            daemon_id,
            obs.get("category", "general"),
            obs.get("observation", obs.get("content", "")),
            obs.get("confidence"),
            json_serialize(obs.get("context")),
            obs.get("source_conversation_id"),
            obs.get("source_journal_date"),
            obs.get("created_at", obs.get("timestamp", datetime.now().isoformat()))
        ))
        count += 1

    print(f"  Migrated {count} self observations")


def migrate_dreams(conn, daemon_id: str):
    """Migrate dreams from data/dreams/"""
    print("\n=== Migrating Dreams ===")
    dreams_dir = DATA_DIR / "dreams"

    if not dreams_dir.exists():
        print("  No dreams directory found")
        return

    count = 0
    for dream_file in dreams_dir.glob("*.json"):
        if dream_file.name == "index.json":
            continue

        dream = load_json(dream_file)
        if not dream:
            continue

        dream_id = dream.get("id", dream_file.stem)

        if record_exists(conn, "dreams", "id", dream_id):
            continue

        conn.execute("""
            INSERT INTO dreams (
                id, daemon_id, date, exchanges_json,
                seeds_json, metadata_json, integration_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dream_id,
            daemon_id,
            dream.get("date", dream_id[:10] if len(dream_id) >= 10 else datetime.now().strftime("%Y-%m-%d")),
            json_serialize(dream.get("exchanges", [])),
            json_serialize(dream.get("seeds")),
            json_serialize(dream.get("metadata")),
            dream.get("integration_status", "pending"),
            dream.get("created_at", datetime.now().isoformat())
        ))
        count += 1

    print(f"  Migrated {count} dreams")


def migrate_solo_reflections(conn, daemon_id: str):
    """Migrate solo reflections"""
    print("\n=== Migrating Solo Reflections ===")
    reflections_dir = DATA_DIR / "solo_reflections"

    if not reflections_dir.exists():
        print("  No solo reflections directory found")
        return

    count = 0
    for ref_file in reflections_dir.glob("*.json"):
        if ref_file.name == "index.json":
            continue

        reflection = load_json(ref_file)
        if not reflection:
            continue

        ref_id = reflection.get("id", ref_file.stem)

        if record_exists(conn, "solo_reflections", "id", ref_id):
            continue

        conn.execute("""
            INSERT INTO solo_reflections (
                id, daemon_id, title, content,
                insights_json, themes_json, duration_minutes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ref_id,
            daemon_id,
            reflection.get("title"),
            reflection.get("content", ""),
            json_serialize(reflection.get("insights")),
            json_serialize(reflection.get("themes")),
            reflection.get("duration_minutes"),
            reflection.get("created_at", datetime.now().isoformat())
        ))
        count += 1

    print(f"  Migrated {count} solo reflections")


def migrate_projects(conn, daemon_id: str):
    """Migrate projects from data/projects/"""
    print("\n=== Migrating Projects ===")
    projects_dir = DATA_DIR / "projects"

    if not projects_dir.exists():
        print("  No projects directory found")
        return

    count = 0
    for proj_file in projects_dir.glob("*.json"):
        if proj_file.name == "index.json":
            continue

        project = load_json(proj_file)
        if not project:
            continue

        proj_id = project.get("id", proj_file.stem)

        if record_exists(conn, "projects", "id", proj_id):
            continue

        conn.execute("""
            INSERT INTO projects (
                id, daemon_id, user_id, name, working_directory,
                description, github_repo, github_token,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proj_id,
            daemon_id,
            project.get("user_id"),
            project.get("name", "Unnamed"),
            project.get("working_directory"),
            project.get("description"),
            project.get("github_repo"),
            project.get("github_token"),
            project.get("created_at", datetime.now().isoformat()),
            project.get("updated_at", datetime.now().isoformat())
        ))

        # Migrate project files
        for pf in project.get("files", []):
            conn.execute("""
                INSERT INTO project_files (
                    project_id, path, description, embedded, added_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                proj_id,
                pf.get("path", ""),
                pf.get("description"),
                1 if pf.get("embedded") else 0,
                pf.get("added_at", datetime.now().isoformat())
            ))

        # Migrate project documents
        for doc in project.get("documents", []):
            doc_id = doc.get("id", str(uuid.uuid4()))
            if not record_exists(conn, "project_documents", "id", doc_id):
                conn.execute("""
                    INSERT INTO project_documents (
                        id, project_id, title, content, created_by,
                        embedded, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc_id,
                    proj_id,
                    doc.get("title", "Untitled"),
                    doc.get("content", ""),
                    doc.get("created_by"),
                    1 if doc.get("embedded") else 0,
                    doc.get("created_at", datetime.now().isoformat()),
                    doc.get("updated_at", datetime.now().isoformat())
                ))

        count += 1
        print(f"  Migrated project: {project.get('name', proj_id[:8])}")

    print(f"  Total projects migrated: {count}")


def migrate_roadmap(conn, daemon_id: str):
    """Migrate roadmap items from data/roadmap/"""
    print("\n=== Migrating Roadmap ===")
    roadmap_dir = DATA_DIR / "roadmap"

    if not roadmap_dir.exists():
        print("  No roadmap directory found")
        return

    # Load index - it's a list of item objects directly
    index = load_json(roadmap_dir / "index.json") or []
    items_dir = roadmap_dir / "items"

    count = 0
    # Index is a list of item objects, not a dict with "items" key
    items_list = index if isinstance(index, list) else []

    for index_item in items_list:
        item_id = index_item.get("id")
        if not item_id:
            continue

        # Try to load detailed item file, fall back to index data
        item_file = items_dir / f"{item_id}.json"
        item = load_json(item_file)

        if not item:
            # Use the index data if no detailed file exists
            item = index_item

        if not item:
            continue

        if record_exists(conn, "roadmap_items", "id", item_id):
            continue

        conn.execute("""
            INSERT INTO roadmap_items (
                id, daemon_id, project_id, title, description,
                status, priority, item_type, assigned_to,
                source_conversation_id, tags_json, created_by,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id,
            daemon_id,
            item.get("project_id"),
            item.get("title", "Untitled"),
            item.get("description"),
            item.get("status", "backlog"),
            item.get("priority", "P2"),
            item.get("item_type", "feature"),
            item.get("assigned_to"),
            item.get("source_conversation_id"),
            json_serialize(item.get("tags")),
            item.get("created_by"),
            item.get("created_at", datetime.now().isoformat()),
            item.get("updated_at", datetime.now().isoformat())
        ))

        # Migrate links
        for link in item.get("links", []):
            conn.execute("""
                INSERT INTO roadmap_links (source_id, target_id, link_type)
                VALUES (?, ?, ?)
            """, (
                item_id,
                link.get("target_id"),
                link.get("link_type", "related")
            ))

        count += 1

    print(f"  Migrated {count} roadmap items")


def migrate_wiki(conn, daemon_id: str):
    """Migrate wiki pages from data/wiki/"""
    print("\n=== Migrating Wiki ===")
    wiki_dir = DATA_DIR / "wiki"

    if not wiki_dir.exists():
        print("  No wiki directory found")
        return

    count = 0
    for category_dir in wiki_dir.iterdir():
        if not category_dir.is_dir():
            continue

        category = category_dir.name

        for wiki_file in category_dir.glob("*.md"):
            # Use filename as ID/slug
            slug = wiki_file.stem
            page_id = f"{category}/{slug}"

            if record_exists(conn, "wiki_pages", "id", page_id):
                continue

            content = wiki_file.read_text()

            # Parse frontmatter if present
            frontmatter = None
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        frontmatter = yaml.safe_load(parts[1])
                        content = parts[2].strip()
                    except yaml.YAMLError:
                        pass

            title = slug.replace("-", " ").replace("_", " ").title()
            if frontmatter and "title" in frontmatter:
                title = frontmatter["title"]

            conn.execute("""
                INSERT INTO wiki_pages (
                    id, daemon_id, category, title, content,
                    frontmatter_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                page_id,
                daemon_id,
                category,
                title,
                content,
                json_serialize(frontmatter),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            count += 1

    print(f"  Migrated {count} wiki pages")


def migrate_goals(conn, daemon_id: str):
    """Migrate goals from data/goals/"""
    print("\n=== Migrating Goals ===")
    goals_dir = DATA_DIR / "goals"

    if not goals_dir.exists():
        print("  No goals directory found")
        return

    # Load initiatives - format is {"initiatives": [...]}
    initiatives_data = load_json(goals_dir / "initiatives.json") or {}
    initiatives = initiatives_data.get("initiatives", []) if isinstance(initiatives_data, dict) else []

    count = 0
    for goal in initiatives:
        goal_id = goal.get("id", str(uuid.uuid4()))

        if record_exists(conn, "goals", "id", goal_id):
            continue

        conn.execute("""
            INSERT INTO goals (
                id, daemon_id, title, description,
                goal_type, status, parent_id, progress_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            goal_id,
            daemon_id,
            goal.get("title", "Untitled"),
            goal.get("description"),
            goal.get("goal_type", goal.get("type", "initiative")),
            goal.get("status", "active"),
            goal.get("parent_id"),
            json_serialize(goal.get("progress")),
            goal.get("created_at", datetime.now().isoformat()),
            goal.get("updated_at")
        ))
        count += 1

    # Also load working_questions as goals - format is {"questions": [...]}
    questions_data = load_json(goals_dir / "working_questions.json") or {}
    questions = questions_data.get("questions", []) if isinstance(questions_data, dict) else []
    for q in questions:
        q_id = q.get("id", str(uuid.uuid4()))

        if record_exists(conn, "goals", "id", q_id):
            continue

        conn.execute("""
            INSERT INTO goals (
                id, daemon_id, title, description,
                goal_type, status, progress_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            q_id,
            daemon_id,
            q.get("question", q.get("title", "Unknown")),
            q.get("context", q.get("description")),
            "question",
            q.get("status", "active"),
            json_serialize(q.get("progress")),
            q.get("created_at", datetime.now().isoformat())
        ))
        count += 1

    print(f"  Migrated {count} goals")


def migrate_rhythm(conn, daemon_id: str):
    """Migrate daily rhythm configuration"""
    print("\n=== Migrating Daily Rhythm ===")
    rhythm_dir = DATA_DIR / "rhythm"

    if not rhythm_dir.exists():
        print("  No rhythm directory found")
        return

    config = load_json(rhythm_dir / "config.json")
    if not config:
        print("  No rhythm config found")
        return

    # Migrate phases
    phase_count = 0
    for phase in config.get("phases", []):
        phase_id = phase.get("id", str(uuid.uuid4()))

        if record_exists(conn, "rhythm_phases", "id", phase_id):
            continue

        conn.execute("""
            INSERT INTO rhythm_phases (
                id, daemon_id, name, activity_type,
                start_time, end_time, description, days_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            phase_id,
            daemon_id,
            phase.get("name", "Unknown"),
            phase.get("activity_type", "general"),
            phase.get("start_time", "00:00"),
            phase.get("end_time", "00:00"),
            phase.get("description"),
            json_serialize(phase.get("days"))
        ))
        phase_count += 1

    # Migrate rhythm records
    records_dir = rhythm_dir / "records"
    record_count = 0
    if records_dir.exists():
        for record_file in records_dir.glob("*.json"):
            records = load_json(record_file)
            if not records:
                continue

            for record in (records if isinstance(records, list) else [records]):
                conn.execute("""
                    INSERT INTO rhythm_records (
                        daemon_id, date, phase_id, status,
                        started_at, completed_at, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    daemon_id,
                    record.get("date", record_file.stem),
                    record.get("phase_id", "unknown"),
                    record.get("status", "pending"),
                    record.get("started_at"),
                    record.get("completed_at"),
                    record.get("notes")
                ))
                record_count += 1

    print(f"  Migrated {phase_count} phases, {record_count} records")


def migrate_usage(conn, daemon_id: str):
    """Migrate token usage logs"""
    print("\n=== Migrating Token Usage ===")
    usage_dir = DATA_DIR / "usage"

    if not usage_dir.exists():
        print("  No usage directory found")
        return

    count = 0
    for usage_file in usage_dir.glob("*.json"):
        date = usage_file.stem
        usage = load_json(usage_file)

        if not usage:
            continue

        # Usage files might be structured differently
        if isinstance(usage, dict):
            for provider, models in usage.items():
                if isinstance(models, dict):
                    for model, stats in models.items():
                        conn.execute("""
                            INSERT INTO token_usage (
                                daemon_id, date, provider, model,
                                input_tokens, output_tokens, cost_usd
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            daemon_id,
                            date,
                            provider,
                            model,
                            stats.get("input_tokens", 0),
                            stats.get("output_tokens", 0),
                            stats.get("cost_usd", 0)
                        ))
                        count += 1

    print(f"  Migrated {count} usage records")


# =============================================================================
# MAIN MIGRATION
# =============================================================================

def run_migration():
    """Run the full migration."""
    print("=" * 60)
    print("CASS VESSEL DATABASE MIGRATION")
    print("=" * 60)
    print(f"Source: {DATA_DIR}")
    print(f"Target: {DATABASE_PATH}")
    print()

    # Initialize database
    init_database()

    # Get or create daemon
    daemon_id = get_or_create_daemon("cass", "temple-codex-1.0")
    print(f"Daemon ID: {daemon_id}")

    with get_db() as conn:
        # Disable foreign keys during migration for flexibility
        conn.execute("PRAGMA foreign_keys = OFF")
        # Run migrations in order (respecting dependencies)
        migrate_users(conn, daemon_id)
        migrate_projects(conn, daemon_id)  # Before conversations (project_id FK)
        migrate_conversations(conn, daemon_id)
        migrate_self_profile(conn, daemon_id)
        migrate_cognitive_snapshots(conn, daemon_id)
        migrate_milestones(conn, daemon_id)
        migrate_self_observations(conn, daemon_id)
        migrate_dreams(conn, daemon_id)
        migrate_solo_reflections(conn, daemon_id)
        migrate_roadmap(conn, daemon_id)
        migrate_wiki(conn, daemon_id)
        migrate_goals(conn, daemon_id)
        migrate_rhythm(conn, daemon_id)
        migrate_usage(conn, daemon_id)

        # Re-enable foreign keys and verify
        conn.execute("PRAGMA foreign_keys = ON")
        # Verify foreign key integrity
        cursor = conn.execute("PRAGMA foreign_key_check")
        violations = cursor.fetchall()
        if violations:
            print(f"\n  Warning: {len(violations)} foreign key violations found")
            for v in violations[:10]:
                print(f"    {v}")

    print()
    print("=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)

    # Print summary
    with get_db() as conn:
        tables = [
            "users", "conversations", "messages", "projects",
            "daemon_profiles", "growth_edges", "opinions",
            "cognitive_snapshots", "milestones", "self_observations",
            "user_observations", "dreams", "solo_reflections",
            "roadmap_items", "wiki_pages", "goals",
            "rhythm_phases", "rhythm_records", "token_usage"
        ]

        print("\nRecord counts:")
        for table in tables:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count}")
            except Exception:
                pass


if __name__ == "__main__":
    run_migration()
