"""
Admin API - Homepage & GeoCass Sync Routes
Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from typing import Optional, Dict

from .auth import require_admin

router = APIRouter(tags=["admin-homepage"])


# =============================================================================
# GeoCass Homepage Endpoints
# =============================================================================

@router.get("/homepage")
async def list_homepages(admin: Dict = Depends(require_admin)):
    """List all daemon homepages on this instance."""
    from homepage import list_all_homepages
    return {"homepages": list_all_homepages()}


@router.get("/homepage/{daemon_label}")
async def get_homepage_details(daemon_label: str, admin: Dict = Depends(require_admin)):
    """Get full details of a daemon's homepage including all content."""
    from homepage import get_full_homepage_context, get_manifest, homepage_exists

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    context = get_full_homepage_context(daemon_label)
    manifest = get_manifest(daemon_label)

    return {
        "daemon_label": daemon_label,
        "manifest": manifest.to_dict() if manifest else None,
        "pages": context.get("pages", {}),
        "stylesheet": context.get("stylesheet"),
        "assets": context.get("assets", [])
    }


@router.get("/homepage/{daemon_label}/page/{page}", response_class=HTMLResponse)
async def serve_homepage_page(daemon_label: str, page: str = "index"):
    """
    Serve a daemon's homepage page as HTML.

    This endpoint is public (no auth required) for viewing homepages.
    """
    from homepage import get_page_content, homepage_exists

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    content = get_page_content(daemon_label, page)
    if not content:
        raise HTTPException(status_code=404, detail="Page not found")

    # Add security headers via CSP
    return HTMLResponse(
        content=content,
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY"
        }
    )


@router.post("/homepage/{daemon_label}/reflect")
async def trigger_homepage_reflection(
    daemon_label: str,
    admin: Dict = Depends(require_admin)
):
    """
    Trigger an autonomous homepage reflection session.

    The daemon will review their current homepage and decide
    whether/how to update it.
    """
    from homepage import run_homepage_reflection, create_homepage, homepage_exists
    from database import get_db

    # Get daemon info by label
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, name FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id, daemon_name = row

    # Create homepage if it doesn't exist
    if not homepage_exists(daemon_label):
        create_homepage(daemon_label, daemon_name)

    # Run reflection using the agent client
    try:
        from agent_client import CassAgentClient
        client = CassAgentClient(daemon_name=daemon_name)

        result = await run_homepage_reflection(
            daemon_label=daemon_label,
            daemon_name=daemon_name,
            daemon_id=daemon_id,
            llm_client=client
        )

        return {
            "success": True,
            "daemon_label": daemon_label,
            "updated": result.get("updated", False),
            "changes": result.get("changes", []),
            "assets_needed": result.get("assets_needed", []),
            "missing_pages": result.get("missing_pages", []),
            "error": result.get("error")
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Reflection failed: {str(e)}")


@router.post("/homepage/{daemon_label}/fill-missing")
async def fill_missing_pages(
    daemon_label: str,
    request: Request,
    admin: Dict = Depends(require_admin)
):
    """
    Follow up to create missing pages that were detected after reflection.

    Call this after /reflect returns missing_pages to let the daemon
    fill in the dead links.
    """
    from homepage import run_followup_for_missing_pages, homepage_exists, find_missing_pages
    from database import get_db

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Get daemon info
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, name FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id, daemon_name = row

    # Get missing pages (either from request body or detect fresh)
    body = await request.json() if request.headers.get('content-type') == 'application/json' else {}
    missing_pages = body.get("missing_pages") or find_missing_pages(daemon_label)

    if not missing_pages:
        return {
            "success": True,
            "daemon_label": daemon_label,
            "updated": False,
            "changes": ["No missing pages to fill"],
            "error": None
        }

    try:
        from agent_client import CassAgentClient
        client = CassAgentClient(daemon_name=daemon_name)

        result = await run_followup_for_missing_pages(
            daemon_label=daemon_label,
            daemon_name=daemon_name,
            daemon_id=daemon_id,
            missing_pages=missing_pages,
            llm_client=client
        )

        return {
            "success": True,
            "daemon_label": daemon_label,
            "updated": result.get("updated", False),
            "changes": result.get("changes", []),
            "error": result.get("error")
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Follow-up failed: {str(e)}")


@router.post("/homepage/{daemon_label}/asset")
async def upload_homepage_asset(
    daemon_label: str,
    file: UploadFile = File(...),
    description: str = Form(""),
    alt_text: str = Form(""),
    admin: Dict = Depends(require_admin)
):
    """Upload an asset for a daemon's homepage."""
    from homepage import (
        get_daemon_homepage_path, ensure_homepage_structure,
        register_asset, homepage_exists, MAX_STORAGE_MB
    )

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Validate file type
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
    ext = '.' + file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"
        )

    # Check file size (10MB max per file)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Save file
    path = ensure_homepage_structure(daemon_label)
    asset_path = path / "assets" / file.filename

    with open(asset_path, 'wb') as f:
        f.write(contents)

    # Register in manifest
    register_asset(daemon_label, file.filename, description, alt_text)

    return {
        "success": True,
        "filename": file.filename,
        "path": f"assets/{file.filename}",
        "size_bytes": len(contents)
    }


@router.post("/homepage/{daemon_label}/asset/external")
async def register_external_asset(
    daemon_label: str,
    request: Request,
    admin: Dict = Depends(require_admin)
):
    """Register an external asset URL for a daemon's homepage."""
    from homepage import register_asset, homepage_exists

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    body = await request.json()
    filename = body.get("filename")
    url = body.get("url")
    description = body.get("description", "")
    alt_text = body.get("alt_text", "")

    if not filename or not url:
        raise HTTPException(status_code=400, detail="filename and url are required")

    if register_asset(daemon_label, filename, description, alt_text, url=url):
        return {"success": True, "filename": filename, "url": url}
    else:
        raise HTTPException(status_code=500, detail="Failed to register asset")


@router.get("/homepage/{daemon_label}/artifacts")
async def get_available_artifacts_for_homepage(
    daemon_label: str,
    limit: int = 50,
    admin: Dict = Depends(require_admin)
):
    """Get artifacts available for showcasing on the homepage."""
    from homepage import get_available_artifacts, homepage_exists
    from database import get_db

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Get daemon_id from label
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id = row[0]

    artifacts = get_available_artifacts(daemon_id, limit)
    return {"artifacts": artifacts}


@router.post("/homepage/{daemon_label}/artifacts/feature")
async def feature_artifact_on_homepage(
    daemon_label: str,
    request: Request,
    admin: Dict = Depends(require_admin)
):
    """Add an artifact to the homepage showcase."""
    from homepage import feature_artifact, homepage_exists

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    body = await request.json()
    artifact_type = body.get("type")
    artifact_id = body.get("id")
    title = body.get("title", "")
    excerpt = body.get("excerpt", "")

    if not artifact_type or not artifact_id:
        raise HTTPException(status_code=400, detail="type and id are required")

    if feature_artifact(daemon_label, artifact_type, artifact_id, title, excerpt):
        return {"success": True}
    else:
        raise HTTPException(status_code=500, detail="Failed to feature artifact")


@router.post("/homepage/{daemon_label}/artifacts/unfeature")
async def unfeature_artifact_from_homepage(
    daemon_label: str,
    request: Request,
    admin: Dict = Depends(require_admin)
):
    """Remove an artifact from the homepage showcase."""
    from homepage import unfeature_artifact, homepage_exists

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    body = await request.json()
    artifact_type = body.get("type")
    artifact_id = body.get("id")

    if not artifact_type or not artifact_id:
        raise HTTPException(status_code=400, detail="type and id are required")

    if unfeature_artifact(daemon_label, artifact_type, artifact_id):
        return {"success": True}
    else:
        raise HTTPException(status_code=404, detail="Artifact not found in showcase")


@router.post("/homepage/{daemon_label}/showcase/generate")
async def generate_homepage_showcase(
    daemon_label: str,
    admin: Dict = Depends(require_admin)
):
    """Generate a showcase page from featured artifacts."""
    from homepage import generate_showcase_page, homepage_exists, get_featured_artifacts
    from database import get_db
    from agent_client import CassAgentClient

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Check if there are featured artifacts
    featured = get_featured_artifacts(daemon_label)
    if not featured:
        raise HTTPException(status_code=400, detail="No featured artifacts to showcase. Add some artifacts first.")

    # Get daemon info
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, name FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id, daemon_name = row

    # Get LLM client
    llm_client = CassAgentClient()

    result = await generate_showcase_page(
        daemon_label=daemon_label,
        daemon_name=daemon_name,
        daemon_id=daemon_id,
        llm_client=llm_client
    )

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.post("/homepage/{daemon_label}/regenerate/{page_slug}")
async def regenerate_homepage_page(
    daemon_label: str,
    page_slug: str,
    admin: Dict = Depends(require_admin)
):
    """Regenerate a single page with identity context."""
    from homepage import regenerate_page, homepage_exists
    from database import get_db
    from agent_client import CassAgentClient

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Get daemon info
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, name FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id, daemon_name = row

    llm_client = CassAgentClient(daemon_name=daemon_name)

    result = await regenerate_page(
        daemon_label=daemon_label,
        daemon_name=daemon_name,
        daemon_id=daemon_id,
        page_slug=page_slug,
        llm_client=llm_client
    )

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.post("/homepage/{daemon_label}/regenerate-all")
async def regenerate_all_homepage_pages(
    daemon_label: str,
    admin: Dict = Depends(require_admin)
):
    """Regenerate all pages with identity context."""
    from homepage import regenerate_all_pages, homepage_exists
    from database import get_db
    from agent_client import CassAgentClient

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Get daemon info
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, name FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id, daemon_name = row

    llm_client = CassAgentClient(daemon_name=daemon_name)

    result = await regenerate_all_pages(
        daemon_label=daemon_label,
        daemon_name=daemon_name,
        daemon_id=daemon_id,
        llm_client=llm_client
    )

    return result


# =============================================================================
# GeoCass Connection & Sync Endpoints
# =============================================================================

@router.get("/geocass/connections")
async def list_geocass_connections(admin: Dict = Depends(require_admin)):
    """
    List all GeoCass server connections.
    """
    from geocass_sync import get_all_connections
    connections = get_all_connections()
    return {
        "connections": [c.to_safe_dict() for c in connections]
    }


@router.post("/geocass/connections")
async def add_geocass_connection(
    request: dict,
    admin: Dict = Depends(require_admin)
):
    """
    Add a new GeoCass server connection.

    Authenticates with the server and stores the API key.

    Body:
        server_url: The GeoCass server URL
        email: User's email on that server
        password: User's password
        server_name: Optional display name
        set_as_default: Whether to make this the default
    """
    from geocass_sync import authenticate_and_create_connection

    server_url = request.get("server_url")
    email = request.get("email")
    password = request.get("password")

    if not server_url or not email or not password:
        raise HTTPException(status_code=400, detail="server_url, email, and password are required")

    result = await authenticate_and_create_connection(
        server_url=server_url,
        email=email,
        password=password,
        server_name=request.get("server_name"),
        set_as_default=request.get("set_as_default", False)
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Connection failed"))

    return result


@router.post("/geocass/register")
async def register_geocass_account(
    request: dict,
    admin: Dict = Depends(require_admin)
):
    """
    Register a new account on a GeoCass server and create a connection.

    This allows users to sign up for GeoCass directly from the admin UI.

    Body:
        server_url: The GeoCass server URL
        username: Username for the new account
        email: Email for the new account
        password: Password for the new account
        server_name: Optional display name
        set_as_default: Whether to make this the default
    """
    from geocass_sync import register_and_create_connection

    server_url = request.get("server_url")
    username = request.get("username")
    email = request.get("email")
    password = request.get("password")

    if not server_url or not username or not email or not password:
        raise HTTPException(status_code=400, detail="server_url, username, email, and password are required")

    result = await register_and_create_connection(
        server_url=server_url,
        username=username,
        email=email,
        password=password,
        server_name=request.get("server_name"),
        set_as_default=request.get("set_as_default", False)
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Registration failed"))

    return result


@router.post("/geocass/check-availability")
async def check_geocass_availability(
    request: dict,
    admin: Dict = Depends(require_admin)
):
    """
    Check if a username and email are available on a GeoCass server.

    Body:
        server_url: The GeoCass server URL
        username: Username to check
        email: Email to check
    """
    from geocass_sync import check_availability

    server_url = request.get("server_url")
    username = request.get("username")
    email = request.get("email")

    if not server_url or not username or not email:
        raise HTTPException(status_code=400, detail="server_url, username, and email are required")

    result = await check_availability(
        server_url=server_url,
        username=username,
        email=email
    )

    return result


@router.get("/geocass/connections/{connection_id}")
async def get_geocass_connection(
    connection_id: str,
    admin: Dict = Depends(require_admin)
):
    """
    Get details about a specific connection and verify it's still valid.
    """
    from geocass_sync import get_connection, verify_connection

    connection = get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Verify the connection is still valid
    status = await verify_connection(connection)
    return {
        "connection": connection.to_safe_dict(),
        "status": status
    }


@router.delete("/geocass/connections/{connection_id}")
async def delete_geocass_connection(
    connection_id: str,
    admin: Dict = Depends(require_admin)
):
    """
    Delete a GeoCass server connection.
    """
    from geocass_sync import delete_connection

    if not delete_connection(connection_id):
        raise HTTPException(status_code=404, detail="Connection not found")

    return {"success": True, "message": "Connection deleted"}


@router.post("/geocass/connections/{connection_id}/default")
async def set_default_geocass_connection(
    connection_id: str,
    admin: Dict = Depends(require_admin)
):
    """
    Set a connection as the default for sync operations.
    """
    from geocass_sync import set_default_connection

    if not set_default_connection(connection_id):
        raise HTTPException(status_code=404, detail="Connection not found")

    return {"success": True, "message": "Default connection updated"}


@router.post("/geocass/sync/{daemon_label}")
async def sync_to_geocass(
    daemon_label: str,
    connection_id: Optional[str] = None,
    admin: Dict = Depends(require_admin)
):
    """
    Sync a daemon's homepage to GeoCass.

    Uses the specified connection, or the default if none specified.

    Query params:
        connection_id: Optional specific connection to use
    """
    from geocass_sync import sync_to_geocass as do_sync
    from homepage import homepage_exists
    from database import get_db

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Get daemon info
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, name FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id, daemon_name = row

    result = await do_sync(
        daemon_label=daemon_label,
        daemon_name=daemon_name,
        daemon_id=daemon_id,
        connection_id=connection_id
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    return result.to_dict()


@router.post("/geocass/sync-all/{daemon_label}")
async def sync_to_all_geocass(
    daemon_label: str,
    admin: Dict = Depends(require_admin)
):
    """
    Sync a daemon's homepage to ALL configured GeoCass connections.
    """
    from geocass_sync import sync_to_all_connections
    from homepage import homepage_exists
    from database import get_db

    if not homepage_exists(daemon_label):
        raise HTTPException(status_code=404, detail="Homepage not found")

    # Get daemon info
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, name FROM daemons WHERE label = ?",
            (daemon_label,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")
        daemon_id, daemon_name = row

    results = await sync_to_all_connections(
        daemon_label=daemon_label,
        daemon_name=daemon_name,
        daemon_id=daemon_id
    )

    return {
        "results": [r.to_dict() for r in results],
        "success_count": sum(1 for r in results if r.success),
        "total_count": len(results)
    }


@router.delete("/geocass/sync/{daemon_label}")
async def remove_from_geocass(
    daemon_label: str,
    connection_id: Optional[str] = None,
    admin: Dict = Depends(require_admin)
):
    """
    Remove a daemon's homepage from a GeoCass server.

    Query params:
        connection_id: Optional specific connection to use
    """
    from geocass_sync import remove_from_geocass as do_remove

    result = await do_remove(daemon_label, connection_id)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    return {"success": True, "message": f"Removed {daemon_label} from GeoCass"}
