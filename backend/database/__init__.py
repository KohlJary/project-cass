"""
Database Module - SQLite connection management and schema

Provides centralized database access for the Cass Vessel backend,
replacing flat JSON/YAML file storage with proper relational database.

Supports multi-daemon architecture via daemon_id foreign keys.

This package maintains backwards compatibility with the original
monolithic database.py module. All public symbols are re-exported here.
"""

# Connection management
from .connection import (
    DATABASE_PATH,
    get_connection,
    close_connection,
    get_db,
)

# Schema
from .schema import (
    SCHEMA_VERSION,
    SCHEMA_SQL,
)

# Utilities
from .utils import (
    dict_from_row,
    json_serialize,
    json_deserialize,
    table_exists,
    get_row_count,
)

# Daemon management
from .daemon import (
    get_or_create_daemon,
    get_daemon_id,
    get_daemon_info,
    get_daemon_entity_name,
)

# Migrations and initialization
from .migrations import (
    init_database,
    init_database_with_migrations,
    migrate_daemon_schema,
    migrate_user_status,
    migrate_daemon_genesis,
)

# Attachment operations
from .attachments_db import (
    save_attachment,
    get_attachment,
    update_attachment_message,
    delete_attachment,
    get_attachments_for_message,
)

# Node chain seeding
from .node_chain import (
    seed_node_templates,
    seed_default_chains,
    initialize_node_chain_system,
)

# Public API
__all__ = [
    # Connection
    "DATABASE_PATH",
    "get_connection",
    "close_connection",
    "get_db",
    # Schema
    "SCHEMA_VERSION",
    "SCHEMA_SQL",
    # Utilities
    "dict_from_row",
    "json_serialize",
    "json_deserialize",
    "table_exists",
    "get_row_count",
    # Daemon
    "get_or_create_daemon",
    "get_daemon_id",
    "get_daemon_info",
    "get_daemon_entity_name",
    # Migrations
    "init_database",
    "init_database_with_migrations",
    "migrate_daemon_schema",
    "migrate_user_status",
    "migrate_daemon_genesis",
    # Attachments
    "save_attachment",
    "get_attachment",
    "update_attachment_message",
    "delete_attachment",
    "get_attachments_for_message",
    # Node chain
    "seed_node_templates",
    "seed_default_chains",
    "initialize_node_chain_system",
]


# Module-level initialization when run directly
if __name__ == "__main__":
    init_database()
    daemon_id = get_or_create_daemon()
    print(f"Default daemon ID: {daemon_id}")
    initialize_node_chain_system(daemon_id)
