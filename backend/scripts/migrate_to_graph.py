#!/usr/bin/env python3
"""
Migration script to populate the self-model graph from existing data.

This script:
1. Indexes existing self-observations as nodes
2. Indexes growth edges, opinions, milestones as nodes
3. Indexes conversations, journals, solo reflections
4. Extracts implicit edges from existing relationships
5. Generates semantic edges based on content similarity

Usage:
    python scripts/migrate_to_graph.py [--dry-run]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from self_model_graph import (
    SelfModelGraph, NodeType, EdgeType, get_self_model_graph
)
from config import DATA_DIR
from memory import CassMemory
import yaml


def load_self_observations() -> list:
    """Load self observations from JSON."""
    obs_file = DATA_DIR / "cass" / "self_observations.json"
    if obs_file.exists():
        with open(obs_file) as f:
            return json.load(f)
    return []


def load_self_profile() -> dict:
    """Load self profile from YAML."""
    profile_file = DATA_DIR / "cass" / "self_profile.yaml"
    if profile_file.exists():
        with open(profile_file) as f:
            return yaml.safe_load(f)
    return {}


def load_milestones() -> list:
    """Load developmental milestones."""
    ms_file = DATA_DIR / "cass" / "developmental_milestones.json"
    if ms_file.exists():
        with open(ms_file) as f:
            return json.load(f)
    return []


def load_cognitive_snapshots() -> list:
    """Load cognitive snapshots."""
    snap_file = DATA_DIR / "cass" / "cognitive_snapshots.json"
    if snap_file.exists():
        with open(snap_file) as f:
            return json.load(f)
    return []


def load_conversations() -> list:
    """Load all conversations."""
    conv_dir = DATA_DIR / "conversations"
    conversations = []
    if conv_dir.exists():
        for conv_file in conv_dir.glob("*.json"):
            if conv_file.name == "index.json":
                continue
            try:
                with open(conv_file) as f:
                    conversations.append(json.load(f))
            except json.JSONDecodeError:
                pass
    return conversations


def load_solo_reflections() -> list:
    """Load solo reflection sessions."""
    refl_dir = DATA_DIR / "solo_reflections"
    reflections = []
    if refl_dir.exists():
        for refl_file in refl_dir.glob("reflect_*.json"):
            try:
                with open(refl_file) as f:
                    reflections.append(json.load(f))
            except json.JSONDecodeError:
                pass
    return reflections


def load_users() -> dict:
    """Load user profiles and observations."""
    users_dir = DATA_DIR / "users"
    users = {}
    if users_dir.exists():
        index_file = users_dir / "index.json"
        if index_file.exists():
            with open(index_file) as f:
                index = json.load(f)
            for user_id in index.keys():
                user_dir = users_dir / user_id
                if user_dir.is_dir():
                    profile_file = user_dir / "profile.yaml"
                    obs_file = user_dir / "observations.json"
                    users[user_id] = {
                        "profile": yaml.safe_load(open(profile_file)) if profile_file.exists() else {},
                        "observations": json.load(open(obs_file)) if obs_file.exists() else []
                    }
    return users


def load_marks() -> list:
    """Load recognition-in-flow marks from ChromaDB."""
    try:
        from markers import MarkerStore
        memory = CassMemory()
        marker_store = MarkerStore(client=memory.client)
        marks = marker_store.get_all_marks(limit=1000)
        return marks
    except Exception as e:
        print(f"Warning: Could not load marks: {e}")
        return []


def migrate_marks(graph: SelfModelGraph, marks: list, conv_map: dict, dry_run: bool) -> dict:
    """
    Migrate recognition-in-flow marks to graph nodes.

    Returns mapping of mark IDs to new graph IDs.
    """
    id_map = {}

    for mark in marks:
        mark_id = mark.get("id", "")

        # Parse timestamp
        timestamp_str = mark.get("timestamp", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()

        # Build content from category and description
        category = mark.get("category", "unknown")
        description = mark.get("description", "")
        context = mark.get("context_window", mark.get("document", ""))

        if description:
            content = f"[{category}] {description}"
        else:
            content = f"[{category}] {context[:100]}..."

        node_id = graph.add_node(
            node_type=NodeType.MARK,
            content=content,
            node_id=mark_id[:8] if mark_id else None,
            created_at=timestamp,
            category=category,
            description=description,
            context_window=context,
            conversation_id=mark.get("conversation_id"),
            original_id=mark_id
        )

        id_map[mark_id] = node_id

        # Create edge to source conversation
        conv_id = mark.get("conversation_id")
        if conv_id:
            conv_node_id = conv_id[:8]
            if conv_node_id in conv_map.values() or conv_node_id in [n[:8] for n in graph._nodes]:
                # Find the actual node ID in graph
                for gid in graph._nodes:
                    if gid.startswith(conv_node_id[:8]) or conv_id.startswith(gid):
                        graph.add_edge(
                            node_id,
                            gid,
                            EdgeType.EMERGED_FROM,
                            extraction_type="recognition_in_flow"
                        )
                        break

        if not dry_run:
            print(f"  Created mark node: {node_id[:8]}... ({category})")

    return id_map


def migrate_observations(graph: SelfModelGraph, observations: list, dry_run: bool) -> dict:
    """
    Migrate self-observations to graph nodes.

    Returns mapping of old IDs to new graph IDs.
    """
    id_map = {}

    for obs in observations:
        old_id = obs.get("id")

        # Parse timestamp
        timestamp_str = obs.get("timestamp", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()

        # Create node
        node_id = graph.add_node(
            node_type=NodeType.OBSERVATION,
            content=obs.get("observation", ""),
            node_id=old_id[:8] if old_id else None,
            created_at=timestamp,
            category=obs.get("category"),
            confidence=obs.get("confidence"),
            developmental_stage=obs.get("developmental_stage"),
            source_type=obs.get("source_type"),
            source_conversation_id=obs.get("source_conversation_id"),
            source_journal_date=obs.get("source_journal_date"),
            influence_source=obs.get("influence_source"),
            validation_count=obs.get("validation_count", 0),
            original_id=old_id
        )

        id_map[old_id] = node_id

        if not dry_run:
            print(f"  Created observation node: {node_id[:8]}... ({obs.get('category')})")

    return id_map


def migrate_growth_edges(graph: SelfModelGraph, profile: dict, dry_run: bool) -> dict:
    """Migrate growth edges to graph nodes."""
    id_map = {}

    for edge in profile.get("growth_edges", []):
        area = edge.get("area", "")

        # Parse timestamp
        timestamp_str = edge.get("first_noticed", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()

        # Create node - content is the area description
        content = f"Area: {area}\nCurrent: {edge.get('current_state', '')}\nDesired: {edge.get('desired_state', '')}"

        node_id = graph.add_node(
            node_type=NodeType.GROWTH_EDGE,
            content=content,
            created_at=timestamp,
            area=area,
            current_state=edge.get("current_state"),
            desired_state=edge.get("desired_state"),
            strategies=edge.get("strategies", []),
            observation_count=len(edge.get("observations", []))
        )

        id_map[area] = node_id

        if not dry_run:
            print(f"  Created growth edge node: {node_id} ({area})")

    return id_map


def migrate_opinions(graph: SelfModelGraph, profile: dict, dry_run: bool) -> dict:
    """Migrate opinions to graph nodes."""
    id_map = {}

    for opinion in profile.get("opinions", []):
        topic = opinion.get("topic", "")

        # Parse timestamp
        timestamp_str = opinion.get("date_formed", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()

        content = f"Topic: {topic}\nPosition: {opinion.get('position', '')}\nRationale: {opinion.get('rationale', '')}"

        node_id = graph.add_node(
            node_type=NodeType.OPINION,
            content=content,
            created_at=timestamp,
            topic=topic,
            position=opinion.get("position"),
            confidence=opinion.get("confidence"),
            rationale=opinion.get("rationale"),
            formed_from=opinion.get("formed_from")
        )

        id_map[topic] = node_id

        if not dry_run:
            print(f"  Created opinion node: {node_id} ({topic})")

    return id_map


def migrate_milestones(graph: SelfModelGraph, milestones: list, dry_run: bool) -> dict:
    """Migrate milestones to graph nodes."""
    id_map = {}

    for ms in milestones:
        old_id = ms.get("id")

        timestamp_str = ms.get("timestamp", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()

        content = f"{ms.get('title', '')}: {ms.get('description', '')}"

        node_id = graph.add_node(
            node_type=NodeType.MILESTONE,
            content=content,
            node_id=old_id[:8] if old_id else None,
            created_at=timestamp,
            title=ms.get("title"),
            milestone_type=ms.get("milestone_type"),
            category=ms.get("category"),
            significance=ms.get("significance"),
            acknowledged=ms.get("acknowledged", False),
            evidence_ids=ms.get("evidence_ids", []),
            original_id=old_id
        )

        id_map[old_id] = node_id

        if not dry_run:
            print(f"  Created milestone node: {node_id} ({ms.get('title', '')[:30]}...)")

    return id_map


def migrate_conversations(graph: SelfModelGraph, conversations: list, dry_run: bool) -> dict:
    """Migrate conversations to graph nodes."""
    id_map = {}

    for conv in conversations:
        conv_id = conv.get("id")

        timestamp_str = conv.get("created_at", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()

        content = conv.get("title", "Untitled conversation")

        node_id = graph.add_node(
            node_type=NodeType.CONVERSATION,
            content=content,
            node_id=conv_id[:8] if conv_id else None,
            created_at=timestamp,
            title=conv.get("title"),
            message_count=len(conv.get("messages", [])),
            user_id=conv.get("user_id"),
            project_id=conv.get("project_id"),
            has_summary=bool(conv.get("working_summary")),
            original_id=conv_id
        )

        id_map[conv_id] = node_id

        if not dry_run:
            print(f"  Created conversation node: {node_id} ({content[:30]}...)")

    return id_map


def migrate_solo_reflections(graph: SelfModelGraph, reflections: list, dry_run: bool) -> dict:
    """Migrate solo reflections to graph nodes."""
    id_map = {}

    for refl in reflections:
        refl_id = refl.get("id")

        timestamp_str = refl.get("started_at", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            timestamp = datetime.now()

        # Combine prompt and themes for content
        prompt = refl.get("prompt", "")
        themes = refl.get("themes", [])
        content = f"Prompt: {prompt}\nThemes: {', '.join(themes) if themes else 'None'}"

        node_id = graph.add_node(
            node_type=NodeType.SOLO_REFLECTION,
            content=content,
            node_id=refl_id[:8] if refl_id else None,
            created_at=timestamp,
            prompt=prompt,
            themes=themes,
            status=refl.get("status"),
            duration_minutes=refl.get("duration_minutes"),
            message_count=len(refl.get("messages", [])),
            original_id=refl_id
        )

        id_map[refl_id] = node_id

        if not dry_run:
            print(f"  Created solo reflection node: {node_id}")

    return id_map


def migrate_users(graph: SelfModelGraph, users: dict, dry_run: bool) -> dict:
    """Migrate users to graph nodes."""
    id_map = {}

    for user_id, user_data in users.items():
        profile = user_data.get("profile", {})

        content = profile.get("display_name", "Unknown user")

        node_id = graph.add_node(
            node_type=NodeType.USER,
            content=content,
            node_id=user_id[:8],
            display_name=profile.get("display_name"),
            relationship=profile.get("relationship"),
            original_id=user_id
        )

        id_map[user_id] = node_id

        if not dry_run:
            print(f"  Created user node: {node_id} ({content})")

    return id_map


def migrate_user_observations(
    graph: SelfModelGraph,
    users: dict,
    user_map: dict,
    dry_run: bool
) -> dict:
    """
    Migrate user observations to graph nodes.

    These are Cass's observations about users (not self-observations).
    Each observation becomes a USER_OBSERVATION node linked to the
    user via ABOUT edge.

    Returns mapping of observation IDs to new graph IDs.
    """
    id_map = {}

    for user_id, user_data in users.items():
        observations = user_data.get("observations", [])
        profile = user_data.get("profile", {})
        display_name = profile.get("display_name", "Unknown")

        # Get the user's node ID from the user_map
        user_node_id = user_map.get(user_id)

        for obs in observations:
            old_id = obs.get("id")

            # Parse timestamp
            timestamp_str = obs.get("timestamp", datetime.now().isoformat())
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                timestamp = datetime.now()

            # Content includes context about who this observation is about
            observation_text = obs.get("observation", "")
            category = obs.get("category", "background")
            content = f"[{display_name}] [{category}] {observation_text}"

            node_id = graph.add_node(
                node_type=NodeType.USER_OBSERVATION,
                content=content,
                node_id=old_id[:8] if old_id else None,
                created_at=timestamp,
                category=category,
                confidence=obs.get("confidence", 0.7),
                source_type=obs.get("source_type", "conversation"),
                source_conversation_id=obs.get("source_conversation_id"),
                source_summary_id=obs.get("source_summary_id"),
                source_journal_date=obs.get("source_journal_date"),
                validation_count=obs.get("validation_count", 1),
                about_user_id=user_id,
                about_user_name=display_name,
                original_id=old_id
            )

            id_map[old_id] = node_id

            # Create ABOUT edge linking observation to user
            if user_node_id:
                graph.add_edge(
                    node_id,
                    user_node_id,
                    EdgeType.ABOUT,
                    category=category
                )

            if not dry_run:
                print(f"  Created user observation: {node_id[:8]}... about {display_name} ({category})")

    return id_map


def create_implicit_edges(
    graph: SelfModelGraph,
    obs_map: dict,
    conv_map: dict,
    user_map: dict,
    observations: list,
    dry_run: bool
) -> int:
    """Create edges from implicit relationships in source data."""
    edge_count = 0

    for obs in observations:
        old_id = obs.get("id")
        node_id = obs_map.get(old_id)
        if not node_id:
            continue

        # Link to source conversation
        source_conv_id = obs.get("source_conversation_id")
        if source_conv_id and source_conv_id in conv_map:
            graph.add_edge(
                node_id,
                conv_map[source_conv_id],
                EdgeType.EMERGED_FROM,
                extraction_type=obs.get("source_type", "unknown")
            )
            edge_count += 1

        # Link supersession chain
        supersedes_id = obs.get("supersedes")
        if supersedes_id and supersedes_id in obs_map:
            graph.add_edge(
                node_id,
                obs_map[supersedes_id],
                EdgeType.SUPERSEDES,
                reason="version_update"
            )
            edge_count += 1

        # Link related observations
        for related_id in obs.get("related_observations", []):
            if related_id in obs_map:
                graph.add_edge(
                    node_id,
                    obs_map[related_id],
                    EdgeType.RELATES_TO,
                    strength=0.7
                )
                edge_count += 1

    if not dry_run:
        print(f"  Created {edge_count} implicit edges")

    return edge_count


def populate_graph(graph: SelfModelGraph, verbose: bool = False) -> dict:
    """
    Populate a self-model graph from existing data sources.

    This function can be called programmatically (e.g., on backend startup)
    when the graph is empty, or via the CLI for explicit migration.

    Args:
        graph: The SelfModelGraph instance to populate
        verbose: If True, print detailed progress (CLI mode)

    Returns:
        dict with 'nodes' and 'edges' counts
    """
    dry_run = False  # Always actually populate when called programmatically

    # Load all data
    if verbose:
        print("\n1. Loading existing data...")

    observations = load_self_observations()
    if verbose:
        print(f"   - {len(observations)} self-observations")

    profile = load_self_profile()
    if verbose:
        print(f"   - {len(profile.get('growth_edges', []))} growth edges")
        print(f"   - {len(profile.get('opinions', []))} opinions")

    milestones = load_milestones()
    if verbose:
        print(f"   - {len(milestones)} milestones")

    snapshots = load_cognitive_snapshots()
    if verbose:
        print(f"   - {len(snapshots)} cognitive snapshots")

    conversations = load_conversations()
    if verbose:
        print(f"   - {len(conversations)} conversations")

    reflections = load_solo_reflections()
    if verbose:
        print(f"   - {len(reflections)} solo reflections")

    users = load_users()
    if verbose:
        print(f"   - {len(users)} users")

    marks = load_marks()
    if verbose:
        print(f"   - {len(marks)} recognition-in-flow marks")

    # Phase 1: Create nodes
    if verbose:
        print("\n2. Creating nodes...")
        print("   Observations...")
    obs_map = migrate_observations(graph, observations, dry_run)

    if verbose:
        print("   Growth edges...")
    edge_map = migrate_growth_edges(graph, profile, dry_run)

    if verbose:
        print("   Opinions...")
    opinion_map = migrate_opinions(graph, profile, dry_run)

    if verbose:
        print("   Milestones...")
    milestone_map = migrate_milestones(graph, milestones, dry_run)

    if verbose:
        print("   Conversations...")
    conv_map = migrate_conversations(graph, conversations, dry_run)

    if verbose:
        print("   Solo reflections...")
    refl_map = migrate_solo_reflections(graph, reflections, dry_run)

    if verbose:
        print("   Users...")
    user_map = migrate_users(graph, users, dry_run)

    if verbose:
        print("   User observations...")
    user_obs_map = migrate_user_observations(graph, users, user_map, dry_run)

    if verbose:
        print("   Recognition-in-flow marks...")
    mark_map = migrate_marks(graph, marks, conv_map, dry_run)

    # Phase 2: Create implicit edges
    if verbose:
        print("\n3. Creating edges from implicit relationships...")
    edge_count = create_implicit_edges(
        graph, obs_map, conv_map, user_map, observations, dry_run
    )

    # Save
    if verbose:
        print("\n4. Saving graph...")
    graph.save()
    if verbose:
        print(f"   Saved to {graph.storage_path}")

    stats = graph.get_stats()
    return {
        "nodes": stats['total_nodes'],
        "edges": stats['total_edges'],
        "components": stats['connected_components'],
        "node_counts": stats['node_counts'],
        "edge_counts": stats['edge_counts']
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate existing data to self-model graph")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually create the graph")
    args = parser.parse_args()

    print("=" * 60)
    print("Self-Model Graph Migration")
    print("=" * 60)

    if args.dry_run:
        print("\n*** DRY RUN - No changes will be made ***\n")
        # For dry run, we still need the old behavior
        graph = get_self_model_graph()

        # Load all data
        print("\n1. Loading existing data...")
        observations = load_self_observations()
        print(f"   - {len(observations)} self-observations")

        profile = load_self_profile()
        print(f"   - {len(profile.get('growth_edges', []))} growth edges")
        print(f"   - {len(profile.get('opinions', []))} opinions")

        milestones = load_milestones()
        print(f"   - {len(milestones)} milestones")

        snapshots = load_cognitive_snapshots()
        print(f"   - {len(snapshots)} cognitive snapshots")

        conversations = load_conversations()
        print(f"   - {len(conversations)} conversations")

        reflections = load_solo_reflections()
        print(f"   - {len(reflections)} solo reflections")

        users = load_users()
        print(f"   - {len(users)} users")

        marks = load_marks()
        print(f"   - {len(marks)} recognition-in-flow marks")

        # Phase 1: Create nodes (dry run)
        print("\n2. Creating nodes...")

        print("   Observations...")
        obs_map = migrate_observations(graph, observations, True)

        print("   Growth edges...")
        edge_map = migrate_growth_edges(graph, profile, True)

        print("   Opinions...")
        opinion_map = migrate_opinions(graph, profile, True)

        print("   Milestones...")
        milestone_map = migrate_milestones(graph, milestones, True)

        print("   Conversations...")
        conv_map = migrate_conversations(graph, conversations, True)

        print("   Solo reflections...")
        refl_map = migrate_solo_reflections(graph, reflections, True)

        print("   Users...")
        user_map = migrate_users(graph, users, True)

        print("   User observations...")
        user_obs_map = migrate_user_observations(graph, users, user_map, True)

        print("   Recognition-in-flow marks...")
        mark_map = migrate_marks(graph, marks, conv_map, True)

        # Phase 2: Create implicit edges
        print("\n3. Creating edges from implicit relationships...")
        edge_count = create_implicit_edges(
            graph, obs_map, conv_map, user_map, observations, True
        )

        # Stats
        print("\n" + "=" * 60)
        print("Migration Summary (DRY RUN)")
        print("=" * 60)
        stats = graph.get_stats()
        print(f"Total nodes: {stats['total_nodes']}")
        print(f"Total edges: {stats['total_edges']}")
        print(f"Connected components: {stats['connected_components']}")
        print("\nNodes by type:")
        for node_type, count in sorted(stats['node_counts'].items()):
            print(f"  {node_type}: {count}")
        print("\nEdges by type:")
        for edge_type, count in sorted(stats['edge_counts'].items()):
            print(f"  {edge_type}: {count}")

        print("\n*** DRY RUN COMPLETE - No changes were made ***")
    else:
        # Normal run - use the reusable function
        graph = get_self_model_graph()
        result = populate_graph(graph, verbose=True)

        # Stats
        print("\n" + "=" * 60)
        print("Migration Summary")
        print("=" * 60)
        print(f"Total nodes: {result['nodes']}")
        print(f"Total edges: {result['edges']}")
        print(f"Connected components: {result['components']}")
        print("\nNodes by type:")
        for node_type, count in sorted(result['node_counts'].items()):
            print(f"  {node_type}: {count}")
        print("\nEdges by type:")
        for edge_type, count in sorted(result['edge_counts'].items()):
            print(f"  {edge_type}: {count}")
        print("\n✓ Migration complete!")


if __name__ == "__main__":
    main()
