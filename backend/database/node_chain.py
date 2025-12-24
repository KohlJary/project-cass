"""
Node Chain Seeding

Functions for seeding node templates and default prompt chains.
"""

import json
from datetime import datetime
from uuid import uuid4

from .connection import get_db


def seed_node_templates() -> int:
    """
    Seed the node_templates table with all system-defined templates.
    Adds new templates even if some already exist (idempotent).
    Returns the number of templates seeded.
    """
    from node_templates import ALL_TEMPLATES

    with get_db() as conn:
        # Get existing template IDs
        cursor = conn.execute("SELECT id FROM node_templates WHERE is_system = 1")
        existing_ids = {row[0] for row in cursor.fetchall()}

        now = datetime.now().isoformat()
        count = 0

        for template in ALL_TEMPLATES:
            if template.id in existing_ids:
                continue  # Already exists, skip

            conn.execute("""
                INSERT INTO node_templates (
                    id, name, slug, category, description, template,
                    params_schema, default_params, is_system, is_locked,
                    default_enabled, default_order, token_estimate,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                template.id,
                template.name,
                template.slug,
                template.category,
                template.description,
                template.template,
                json.dumps(template.params_schema) if template.params_schema else None,
                json.dumps(template.default_params) if template.default_params else None,
                1 if template.is_system else 0,
                1 if template.is_locked else 0,
                1 if template.default_enabled else 0,
                template.default_order,
                template.token_estimate,
                now,
                now,
            ))
            count += 1

        if count > 0:
            print(f"Seeded {count} new node templates")
        return count


def seed_default_chains(daemon_id: str) -> int:
    """
    Seed default prompt chains for a daemon.
    Returns the number of chains created.
    """
    from chain_assembler import (
        build_standard_chain,
        build_lightweight_chain,
        build_research_chain,
        build_relational_chain,
    )

    with get_db() as conn:
        # Check if chains already exist for this daemon
        cursor = conn.execute(
            "SELECT COUNT(*) FROM prompt_chains WHERE daemon_id = ? AND is_default = 1",
            (daemon_id,)
        )
        existing = cursor.fetchone()[0]
        if existing > 0:
            return 0  # Already seeded

        now = datetime.now().isoformat()

        presets = [
            ("Standard", "Full capabilities - all tools and features enabled", build_standard_chain, True),
            ("Lightweight", "Minimal token usage - essential components only", build_lightweight_chain, False),
            ("Research Mode", "Research-focused - wiki, documents, visible thinking", build_research_chain, False),
            ("Relational Mode", "Connection-focused - user models, dreams, journals", build_relational_chain, False),
        ]

        count = 0
        for name, description, builder, is_active in presets:
            chain_id = str(uuid4())

            # Create chain
            conn.execute("""
                INSERT INTO prompt_chains (
                    id, daemon_id, name, description, is_active, is_default,
                    created_at, updated_at, created_by
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'system')
            """, (chain_id, daemon_id, name, description, 1 if is_active else 0, now, now))

            # Build and insert nodes
            nodes = builder(daemon_id)
            for node in nodes:
                conn.execute("""
                    INSERT INTO chain_nodes (
                        id, chain_id, template_id, params, order_index,
                        enabled, locked, conditions, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.id,
                    chain_id,
                    node.template_id,
                    json.dumps(node.params) if node.params else None,
                    node.order_index,
                    1 if node.enabled else 0,
                    1 if node.locked else 0,
                    json.dumps([c.to_dict() for c in node.conditions]) if node.conditions else None,
                    now,
                    now,
                ))

            count += 1

        print(f"Seeded {count} default prompt chains for daemon {daemon_id}")
        return count


def initialize_node_chain_system(daemon_id: str) -> None:
    """
    Initialize the node chain system for a daemon.
    Seeds templates and default chains if needed.
    """
    seed_node_templates()
    seed_default_chains(daemon_id)
