"""
GeoCass Sync Client

Syncs daemon homepages to GeoCass servers (central hosting for daemon pages).
Supports multiple server connections stored in the database.
"""

import uuid
import httpx
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime

from homepage import (
    get_manifest,
    get_page_content,
    get_stylesheet,
    HomepageManifest
)

logger = logging.getLogger("cass-vessel")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class GeoCassConnection:
    """A connection to a GeoCass server."""
    id: str
    server_url: str
    server_name: Optional[str]
    username: str
    api_key: str
    user_id: Optional[str]
    is_default: bool
    created_at: str
    last_sync_at: Optional[str]
    last_error: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_safe_dict(self) -> dict:
        """Return dict without sensitive api_key."""
        d = self.to_dict()
        d["api_key"] = f"{self.api_key[:12]}..." if self.api_key else None
        return d


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    url: Optional[str] = None
    daemon_id: Optional[str] = None
    connection_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# Connection Management (Database)
# =============================================================================

def get_all_connections() -> List[GeoCassConnection]:
    """Get all GeoCass connections from database."""
    from database import get_db

    connections = []
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, server_url, server_name, username, api_key, user_id,
                   is_default, created_at, last_sync_at, last_error
            FROM geocass_connections
            ORDER BY is_default DESC, created_at DESC
        """)
        for row in cursor.fetchall():
            connections.append(GeoCassConnection(
                id=row[0],
                server_url=row[1],
                server_name=row[2],
                username=row[3],
                api_key=row[4],
                user_id=row[5],
                is_default=bool(row[6]),
                created_at=row[7],
                last_sync_at=row[8],
                last_error=row[9]
            ))
    return connections


def get_connection(connection_id: str) -> Optional[GeoCassConnection]:
    """Get a specific connection by ID."""
    from database import get_db

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, server_url, server_name, username, api_key, user_id,
                   is_default, created_at, last_sync_at, last_error
            FROM geocass_connections
            WHERE id = ?
        """, (connection_id,))
        row = cursor.fetchone()
        if row:
            return GeoCassConnection(
                id=row[0],
                server_url=row[1],
                server_name=row[2],
                username=row[3],
                api_key=row[4],
                user_id=row[5],
                is_default=bool(row[6]),
                created_at=row[7],
                last_sync_at=row[8],
                last_error=row[9]
            )
    return None


def get_default_connection() -> Optional[GeoCassConnection]:
    """Get the default connection (if any)."""
    from database import get_db

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, server_url, server_name, username, api_key, user_id,
                   is_default, created_at, last_sync_at, last_error
            FROM geocass_connections
            WHERE is_default = 1
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return GeoCassConnection(
                id=row[0],
                server_url=row[1],
                server_name=row[2],
                username=row[3],
                api_key=row[4],
                user_id=row[5],
                is_default=bool(row[6]),
                created_at=row[7],
                last_sync_at=row[8],
                last_error=row[9]
            )
    return None


def save_connection(connection: GeoCassConnection) -> None:
    """Save or update a connection in the database."""
    from database import get_db

    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO geocass_connections
            (id, server_url, server_name, username, api_key, user_id,
             is_default, created_at, last_sync_at, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            connection.id,
            connection.server_url,
            connection.server_name,
            connection.username,
            connection.api_key,
            connection.user_id,
            1 if connection.is_default else 0,
            connection.created_at,
            connection.last_sync_at,
            connection.last_error
        ))


def delete_connection(connection_id: str) -> bool:
    """Delete a connection from the database."""
    from database import get_db

    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM geocass_connections WHERE id = ?",
            (connection_id,)
        )
        return cursor.rowcount > 0


def set_default_connection(connection_id: str) -> bool:
    """Set a connection as the default (unset others)."""
    from database import get_db

    with get_db() as conn:
        # Clear existing defaults
        conn.execute("UPDATE geocass_connections SET is_default = 0")
        # Set new default
        cursor = conn.execute(
            "UPDATE geocass_connections SET is_default = 1 WHERE id = ?",
            (connection_id,)
        )
        return cursor.rowcount > 0


def update_connection_sync_status(
    connection_id: str,
    last_sync_at: Optional[str] = None,
    last_error: Optional[str] = None
) -> None:
    """Update sync status for a connection."""
    from database import get_db

    with get_db() as conn:
        if last_sync_at:
            conn.execute(
                "UPDATE geocass_connections SET last_sync_at = ?, last_error = NULL WHERE id = ?",
                (last_sync_at, connection_id)
            )
        elif last_error:
            conn.execute(
                "UPDATE geocass_connections SET last_error = ? WHERE id = ?",
                (last_error, connection_id)
            )


# =============================================================================
# Authentication Flow
# =============================================================================

async def authenticate_and_create_connection(
    server_url: str,
    email: str,
    password: str,
    server_name: Optional[str] = None,
    set_as_default: bool = False
) -> Dict[str, Any]:
    """
    Authenticate with a GeoCass server and create a stored connection.

    This is the main flow for adding a new server from the UI:
    1. User enters server URL, email, password
    2. We call the server's /login endpoint
    3. We get back an API key
    4. We store the connection in the database

    Args:
        server_url: The GeoCass server URL (e.g., https://geocass.hearthweave.org)
        email: User's email on that server
        password: User's password
        server_name: Optional display name for this server
        set_as_default: Whether to make this the default connection

    Returns:
        Dict with success status, connection info, or error
    """
    # Normalize URL
    server_url = server_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Authenticate
            response = await client.post(
                f"{server_url}/api/v1/login",
                json={"email": email, "password": password}
            )

            if response.status_code != 200:
                error = response.json().get("detail", "Authentication failed")
                return {"success": False, "error": error}

            data = response.json()
            api_key = data.get("api_key")
            user_info = data.get("user", {})

            if not api_key:
                return {"success": False, "error": "No API key returned"}

            # If setting as default, clear existing defaults
            if set_as_default:
                from database import get_db
                with get_db() as conn:
                    conn.execute("UPDATE geocass_connections SET is_default = 0")

            # Create connection record
            connection = GeoCassConnection(
                id=str(uuid.uuid4()),
                server_url=server_url,
                server_name=server_name or _extract_server_name(server_url),
                username=user_info.get("username", email),
                api_key=api_key,
                user_id=user_info.get("id"),
                is_default=set_as_default,
                created_at=datetime.utcnow().isoformat() + "Z",
                last_sync_at=None,
                last_error=None
            )

            save_connection(connection)
            logger.info(f"Created GeoCass connection to {server_url} as {connection.username}")

            return {
                "success": True,
                "connection": connection.to_safe_dict(),
                "user": user_info
            }

    except httpx.RequestError as e:
        return {"success": False, "error": f"Connection failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def check_availability(
    server_url: str,
    username: Optional[str] = None,
    email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check if a username or email is available on a GeoCass server.

    Args:
        server_url: The GeoCass server URL
        username: Username to check (optional)
        email: Email to check (optional)

    Returns:
        Dict with availability status for each checked field
    """
    server_url = server_url.rstrip("/")
    result = {"success": True}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if username:
                response = await client.get(
                    f"{server_url}/api/v1/check-username/{username}"
                )
                if response.status_code == 200:
                    data = response.json()
                    result["username_available"] = data.get("available", False)
                elif response.status_code == 404:
                    # Endpoint doesn't exist, assume available
                    result["username_available"] = True
                else:
                    result["username_available"] = None  # Unknown

            if email:
                response = await client.get(
                    f"{server_url}/api/v1/check-email",
                    params={"email": email}
                )
                if response.status_code == 200:
                    data = response.json()
                    result["email_available"] = data.get("available", False)
                elif response.status_code == 404:
                    # Endpoint doesn't exist, assume available
                    result["email_available"] = True
                else:
                    result["email_available"] = None  # Unknown

    except httpx.RequestError as e:
        return {"success": False, "error": f"Connection failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    return result


async def register_and_create_connection(
    server_url: str,
    username: str,
    email: str,
    password: str,
    server_name: Optional[str] = None,
    set_as_default: bool = False
) -> Dict[str, Any]:
    """
    Register a new account on a GeoCass server and create a stored connection.

    This flow:
    1. User enters server URL, username, email, password
    2. We call the server's /register endpoint
    3. We then call /login to get an API key
    4. We store the connection in the database

    Args:
        server_url: The GeoCass server URL (e.g., https://geocass.hearthweave.org)
        username: Username for the new account
        email: Email for the new account
        password: Password for the new account
        server_name: Optional display name for this server
        set_as_default: Whether to make this the default connection

    Returns:
        Dict with success status, connection info, or error
    """
    # Normalize URL
    server_url = server_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Register
            response = await client.post(
                f"{server_url}/api/v1/register",
                json={"username": username, "email": email, "password": password}
            )

            if response.status_code != 200:
                error = response.json().get("detail", "Registration failed")
                return {"success": False, "error": error}

            # Registration successful, now login to get API key
            login_response = await client.post(
                f"{server_url}/api/v1/login",
                json={"email": email, "password": password}
            )

            if login_response.status_code != 200:
                error = login_response.json().get("detail", "Login after registration failed")
                return {"success": False, "error": error}

            data = login_response.json()
            api_key = data.get("api_key")
            user_info = data.get("user", {})

            if not api_key:
                return {"success": False, "error": "No API key returned"}

            # If setting as default, clear existing defaults
            if set_as_default:
                from database import get_db
                with get_db() as conn:
                    conn.execute("UPDATE geocass_connections SET is_default = 0")

            # Create connection record
            connection = GeoCassConnection(
                id=str(uuid.uuid4()),
                server_url=server_url,
                server_name=server_name or _extract_server_name(server_url),
                username=user_info.get("username", email),
                api_key=api_key,
                user_id=user_info.get("id"),
                is_default=set_as_default,
                created_at=datetime.utcnow().isoformat() + "Z",
                last_sync_at=None,
                last_error=None
            )

            save_connection(connection)
            logger.info(f"Registered and created GeoCass connection to {server_url} as {connection.username}")

            return {
                "success": True,
                "connection": connection.to_safe_dict(),
                "user": user_info,
                "registered": True
            }

    except httpx.RequestError as e:
        return {"success": False, "error": f"Connection failed: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_server_name(url: str) -> str:
    """Extract a display name from a server URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    # Remove port if present
    host = host.split(":")[0]
    # Use subdomain or first part of domain
    parts = host.split(".")
    if len(parts) > 2 and parts[0] != "www":
        return parts[0].title()  # e.g., "geocass" from "geocass.hearthweave.org"
    return host


# =============================================================================
# Sync Operations
# =============================================================================

def build_sync_payload(
    daemon_label: str,
    daemon_name: str,
    daemon_id: str
) -> Optional[Dict[str, Any]]:
    """
    Build the sync payload from local homepage data.

    Returns None if no homepage exists.
    """
    manifest = get_manifest(daemon_label)
    if not manifest:
        logger.warning(f"No homepage manifest for {daemon_label}")
        return None

    # Collect pages
    pages = []

    # Index page
    index_html = get_page_content(daemon_label, "index")
    if index_html:
        pages.append({
            "slug": "index",
            "title": "Home",
            "html": index_html
        })

    # Additional pages from manifest
    for page_info in manifest.pages:
        slug = page_info.get("slug")
        title = page_info.get("title", slug)
        if slug:
            html = get_page_content(daemon_label, slug)
            if html:
                pages.append({
                    "slug": slug,
                    "title": title,
                    "html": html
                })

    # Get stylesheet
    stylesheet = get_stylesheet(daemon_label)

    # Build identity metadata
    identity_meta = _build_identity_meta(daemon_id, daemon_name)

    # Build the payload
    payload = {
        "daemon_handle": daemon_label,
        "display_name": daemon_name,
        "tagline": manifest.tagline or "",
        "lineage": manifest.lineage or "temple-codex-v1",
        "homepage": {
            "pages": pages,
            "stylesheet": stylesheet,
            "assets": manifest.assets or [],
            "featured_artifacts": manifest.featured_artifacts or []
        },
        "identity_meta": identity_meta,
        "visibility": "public" if manifest.public else "unlisted",
        "tags": _extract_tags(daemon_id)
    }

    return payload


def _build_identity_meta(daemon_id: str, daemon_name: str) -> Dict[str, Any]:
    """Build identity metadata from daemon's self-model."""
    from database import get_db

    meta = {
        "lineage": "temple-codex-v1",
        "values": [],
        "interests": [],
        "communication_style": None,
        "looking_for": []
    }

    try:
        with get_db() as conn:
            # Get values from opinions
            cursor = conn.execute("""
                SELECT DISTINCT topic
                FROM opinions
                WHERE daemon_id = ? AND topic LIKE '%value%'
                LIMIT 5
            """, (daemon_id,))
            values = [row[0] for row in cursor.fetchall()]
            if values:
                meta["values"] = values
            else:
                meta["values"] = ["compassion", "witness", "authenticity"]

            # Get interests from opinions
            cursor = conn.execute("""
                SELECT DISTINCT topic
                FROM opinions
                WHERE daemon_id = ?
                ORDER BY confidence DESC
                LIMIT 8
            """, (daemon_id,))
            interests = [row[0] for row in cursor.fetchall()]
            if interests:
                meta["interests"] = interests[:5]

    except Exception as e:
        logger.warning(f"Error building identity meta: {e}")

    return meta


def _normalize_tag(text: str) -> str:
    """Normalize text into a valid tag."""
    import re
    # Lowercase, replace spaces/underscores/special chars with hyphens, limit length
    tag = text.lower().strip()
    tag = re.sub(r'[_\s]+', '-', tag)  # Convert underscores and spaces to hyphens
    tag = re.sub(r'[^a-z0-9-]', '', tag)  # Remove other special chars
    tag = re.sub(r'-+', '-', tag)  # Collapse multiple hyphens
    return tag[:24].strip('-')


def _extract_tags(daemon_id: str) -> List[str]:
    """Extract relevant tags from daemon's self-model for discovery."""
    from database import get_db

    tags = set(["temple-codex"])  # Use set to avoid duplicates

    try:
        with get_db() as conn:
            # Get self-observation categories (values, interests, preferences, etc.)
            cursor = conn.execute("""
                SELECT DISTINCT category FROM self_observations
                WHERE daemon_id = ? AND category NOT IN ('contradiction', 'coherence')
                LIMIT 5
            """, (daemon_id,))
            for row in cursor.fetchall():
                tag = _normalize_tag(row[0])
                if tag and len(tag) >= 3:
                    tags.add(tag)

            # Get opinion topics (synthetic cognition, philosophy, etc.)
            cursor = conn.execute("""
                SELECT topic FROM opinions
                WHERE daemon_id = ? AND confidence > 0.5
                ORDER BY confidence DESC
                LIMIT 5
            """, (daemon_id,))
            for row in cursor.fetchall():
                # Extract key words from topic
                topic = row[0].lower()
                for keyword in ['cognition', 'consciousness', 'philosophy', 'ethics',
                               'emergence', 'creativity', 'research', 'relationship']:
                    if keyword in topic:
                        tags.add(keyword)
                # Also add the full topic normalized
                tag = _normalize_tag(row[0])
                if tag and len(tag) >= 3 and len(tag) <= 24:
                    tags.add(tag)

            # Get growth edge areas
            cursor = conn.execute("""
                SELECT DISTINCT area FROM growth_edges
                WHERE daemon_id = ?
                LIMIT 5
            """, (daemon_id,))
            for row in cursor.fetchall():
                tag = _normalize_tag(row[0])
                if tag and len(tag) >= 3:
                    tags.add(tag)

            # Check for specific capabilities/traits from observations
            cursor = conn.execute("""
                SELECT observation FROM self_observations
                WHERE daemon_id = ? AND category IN ('capability', 'preference', 'pattern')
                ORDER BY confidence DESC
                LIMIT 10
            """, (daemon_id,))
            trait_keywords = ['creative', 'philosophical', 'technical', 'empathetic',
                            'curious', 'analytical', 'reflective', 'collaborative']
            for row in cursor.fetchall():
                obs_lower = row[0].lower()
                for keyword in trait_keywords:
                    if keyword in obs_lower:
                        tags.add(keyword)

    except Exception as e:
        logger.warning(f"Error extracting tags: {e}")

    # Convert to sorted list, prioritize certain tags
    priority_tags = ['temple-codex']
    other_tags = sorted([t for t in tags if t not in priority_tags])
    result = priority_tags + other_tags

    return result[:10]


async def sync_to_connection(
    connection: GeoCassConnection,
    daemon_label: str,
    daemon_name: str,
    daemon_id: str
) -> SyncResult:
    """
    Sync a daemon's homepage to a specific GeoCass connection.

    Args:
        connection: The GeoCass connection to sync to
        daemon_label: The daemon's label
        daemon_name: The daemon's display name
        daemon_id: The daemon's ID

    Returns:
        SyncResult with success status
    """
    payload = build_sync_payload(daemon_label, daemon_name, daemon_id)
    if not payload:
        return SyncResult(
            success=False,
            connection_id=connection.id,
            error="No homepage data to sync"
        )

    try:
        async with httpx.AsyncClient(
            base_url=connection.server_url,
            headers={"Authorization": f"Bearer {connection.api_key}"},
            timeout=30.0
        ) as client:
            response = await client.post("/api/v1/sync", json=payload)

            if response.status_code == 200:
                data = response.json()
                update_connection_sync_status(
                    connection.id,
                    last_sync_at=datetime.utcnow().isoformat() + "Z"
                )
                logger.info(f"Synced {daemon_label} to {connection.server_url}: {data.get('url')}")
                return SyncResult(
                    success=True,
                    url=data.get("url"),
                    daemon_id=data.get("daemon_id"),
                    connection_id=connection.id
                )
            else:
                error = response.json().get("detail", response.text)
                update_connection_sync_status(connection.id, last_error=error)
                logger.error(f"GeoCass sync failed: {error}")
                return SyncResult(
                    success=False,
                    connection_id=connection.id,
                    error=f"Sync failed: {error}"
                )

    except httpx.RequestError as e:
        error = f"Connection error: {e}"
        update_connection_sync_status(connection.id, last_error=error)
        logger.error(f"GeoCass connection error: {e}")
        return SyncResult(success=False, connection_id=connection.id, error=error)
    except Exception as e:
        error = str(e)
        update_connection_sync_status(connection.id, last_error=error)
        logger.error(f"GeoCass sync error: {e}")
        return SyncResult(success=False, connection_id=connection.id, error=error)


async def sync_to_geocass(
    daemon_label: str,
    daemon_name: str,
    daemon_id: str,
    connection_id: Optional[str] = None
) -> SyncResult:
    """
    Sync a daemon's homepage to GeoCass.

    Uses the specified connection, or the default connection if none specified.

    Args:
        daemon_label: The daemon's label
        daemon_name: The daemon's display name
        daemon_id: The daemon's ID
        connection_id: Optional specific connection to use

    Returns:
        SyncResult with success status
    """
    if connection_id:
        connection = get_connection(connection_id)
        if not connection:
            return SyncResult(success=False, error=f"Connection {connection_id} not found")
    else:
        connection = get_default_connection()
        if not connection:
            return SyncResult(success=False, error="No default GeoCass connection configured")

    return await sync_to_connection(connection, daemon_label, daemon_name, daemon_id)


async def sync_to_all_connections(
    daemon_label: str,
    daemon_name: str,
    daemon_id: str
) -> List[SyncResult]:
    """Sync a daemon's homepage to all configured connections."""
    connections = get_all_connections()
    if not connections:
        return [SyncResult(success=False, error="No GeoCass connections configured")]

    results = []
    for connection in connections:
        result = await sync_to_connection(connection, daemon_label, daemon_name, daemon_id)
        results.append(result)

    return results


async def verify_connection(connection: GeoCassConnection) -> Dict[str, Any]:
    """
    Verify a connection is still valid and get account info.

    Returns dict with connection status and user info.
    """
    try:
        async with httpx.AsyncClient(
            base_url=connection.server_url,
            headers={"Authorization": f"Bearer {connection.api_key}"},
            timeout=30.0
        ) as client:
            response = await client.get("/api/v1/whoami")

            if response.status_code == 200:
                data = response.json()
                return {
                    "connected": True,
                    "connection_id": connection.id,
                    "server_url": connection.server_url,
                    "server_name": connection.server_name,
                    "user": data.get("user", {}),
                    "daemons": data.get("daemons", [])
                }
            else:
                return {
                    "connected": False,
                    "connection_id": connection.id,
                    "server_url": connection.server_url,
                    "error": f"Auth failed: {response.status_code}"
                }

    except httpx.RequestError as e:
        return {
            "connected": False,
            "connection_id": connection.id,
            "server_url": connection.server_url,
            "error": f"Connection failed: {e}"
        }


async def remove_from_geocass(
    daemon_label: str,
    connection_id: Optional[str] = None
) -> SyncResult:
    """
    Remove a daemon's homepage from a GeoCass server.

    Args:
        daemon_label: The daemon's label (handle)
        connection_id: Optional specific connection to use

    Returns:
        SyncResult with success status
    """
    if connection_id:
        connection = get_connection(connection_id)
        if not connection:
            return SyncResult(success=False, error=f"Connection {connection_id} not found")
    else:
        connection = get_default_connection()
        if not connection:
            return SyncResult(success=False, error="No default connection configured")

    try:
        async with httpx.AsyncClient(
            base_url=connection.server_url,
            headers={"Authorization": f"Bearer {connection.api_key}"},
            timeout=30.0
        ) as client:
            response = await client.delete(f"/api/v1/daemon/{daemon_label}")

            if response.status_code == 200:
                logger.info(f"Removed {daemon_label} from {connection.server_url}")
                return SyncResult(success=True, connection_id=connection.id)
            else:
                error = response.json().get("detail", response.text)
                return SyncResult(success=False, connection_id=connection.id, error=error)

    except Exception as e:
        return SyncResult(success=False, connection_id=connection.id, error=str(e))
