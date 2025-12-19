"""
Admin API - Daemon Management Routes
Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any
from pydantic import BaseModel
from pathlib import Path
import tempfile
import shutil

from .auth import require_admin, require_auth

router = APIRouter(tags=["admin-daemons"])


# ============== Helper Functions ==============

def get_effective_daemon_id(daemon_id: Optional[str] = None) -> str:
    """Get effective daemon ID - uses provided one or falls back to global default."""
    if daemon_id:
        return daemon_id
    from database import get_daemon_id
    return get_daemon_id()


# ============== Pydantic Models ==============

class GenesisJsonImportRequest(BaseModel):
    json_data: Dict[str, Any]
    merge_existing: bool = False


# ============== Daemon CRUD Endpoints ==============

@router.get("/daemons")
async def list_daemons(user: Dict = Depends(require_auth)):
    """List all available daemons. Available to any authenticated user."""
    from database import get_db
    # Note: user dependency injected from parent router

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, label, name, created_at, kernel_version, status, activity_mode
            FROM daemons
            ORDER BY label
        """)

        columns = ["id", "label", "name", "created_at", "kernel_version", "status", "activity_mode"]
        daemons = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {"daemons": daemons}


@router.get("/daemons/mine")
async def get_my_daemons(user: Dict = Depends(require_auth)):
    """Get daemons available to the current user: Cass + their genesis daemons."""
    from database import get_db

    user_id = user["user_id"]

    with get_db() as conn:
        # Always include Cass (label='cass') and user's own daemons
        cursor = conn.execute("""
            SELECT DISTINCT d.id, d.label, d.name, d.birth_type, d.created_at,
                   d.kernel_version, d.status, d.activity_mode
            FROM daemons d
            WHERE d.label = 'cass'  -- Always include Cass
               OR d.id IN (
                   -- Daemons with user observations about this user
                   SELECT DISTINCT daemon_id FROM user_observations WHERE user_id = ?
                   UNION
                   -- Daemons user has conversed with
                   SELECT DISTINCT daemon_id FROM conversations WHERE user_id = ?
                   UNION
                   -- Daemons user created via genesis
                   SELECT DISTINCT d2.id FROM daemons d2
                   JOIN genesis_dreams g ON g.id = d2.genesis_dream_id
                   WHERE g.user_id = ?
               )
            ORDER BY CASE WHEN d.label = 'cass' THEN 0 ELSE 1 END, d.created_at DESC
        """, (user_id, user_id, user_id))

        daemons = []
        for row in cursor.fetchall():
            daemons.append({
                "id": row["id"],
                "label": row["label"],
                "name": row["name"],
                "birth_type": row["birth_type"],
                "created_at": row["created_at"],
                "kernel_version": row["kernel_version"],
                "status": row["status"],
                "activity_mode": row["activity_mode"],
            })

    return {"daemons": daemons, "count": len(daemons)}


@router.get("/daemons/{daemon_id}")
async def get_daemon(daemon_id: str, admin: Dict = Depends(require_admin)):
    """Get details for a specific daemon."""
    from database import get_db

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, label, name, created_at, kernel_version, status, activity_mode
            FROM daemons
            WHERE id = ?
        """, (daemon_id,))

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")

        columns = ["id", "label", "name", "created_at", "kernel_version", "status", "activity_mode"]
        daemon = dict(zip(columns, row))

        # Get some stats for this daemon
        stats_cursor = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM conversations WHERE daemon_id = ?) as conversations,
                (SELECT COUNT(*) FROM wiki_pages WHERE daemon_id = ?) as wiki_pages,
                (SELECT COUNT(*) FROM journals WHERE daemon_id = ?) as journals,
                (SELECT COUNT(*) FROM dreams WHERE daemon_id = ?) as dreams
        """, (daemon_id, daemon_id, daemon_id, daemon_id))

        stats_row = stats_cursor.fetchone()
        daemon["stats"] = {
            "conversations": stats_row[0] or 0,
            "wiki_pages": stats_row[1] or 0,
            "journals": stats_row[2] or 0,
            "dreams": stats_row[3] or 0,
        }

    return daemon


@router.patch("/daemons/{daemon_id}/activity-mode")
async def update_daemon_activity_mode(
    daemon_id: str,
    request: Request,
    admin: Dict = Depends(require_admin)
):
    """Update a daemon's activity mode (active/dormant)."""
    from database import get_db

    body = await request.json()
    activity_mode = body.get("activity_mode")

    if activity_mode not in ("active", "dormant"):
        raise HTTPException(
            status_code=400,
            detail="activity_mode must be 'active' or 'dormant'"
        )

    with get_db() as conn:
        # Verify daemon exists
        cursor = conn.execute("SELECT id FROM daemons WHERE id = ?", (daemon_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Daemon not found")

        # Update activity mode
        conn.execute(
            "UPDATE daemons SET activity_mode = ? WHERE id = ?",
            (activity_mode, daemon_id)
        )
        conn.commit()

    return {"success": True, "daemon_id": daemon_id, "activity_mode": activity_mode}


@router.delete("/daemons/{daemon_id}")
async def delete_daemon_endpoint(
    daemon_id: str,
    admin: Dict = Depends(require_admin)
):
    """Delete a daemon and all its associated data. Admin only."""
    from daemon_export import delete_daemon

    # Extra safety: require is_admin flag
    if not admin.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required to delete daemons")

    try:
        result = delete_daemon(daemon_id, confirm=True)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete daemon: {str(e)}")


# ============== Daemon Export/Import Endpoints ==============

@router.get("/daemons/exports/seeds")
async def list_seed_exports(admin: Dict = Depends(require_admin)):
    """List available .anima exports from seed folder."""
    from daemon_export import list_seed_exports

    exports = list_seed_exports()
    return {"exports": exports}


@router.post("/daemons/{daemon_id}/export")
async def export_daemon_endpoint(
    daemon_id: str,
    admin: Dict = Depends(require_admin)
):
    """Export a daemon to downloadable .anima file."""
    from daemon_export import export_daemon, ANIMA_EXTENSION

    # Export to temp file
    with tempfile.NamedTemporaryFile(suffix=ANIMA_EXTENSION, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = export_daemon(daemon_id, tmp_path)
        daemon_label = result["daemon_label"]
        timestamp = result.get("stats", {}).get("exported_at", "export")

        # Return as file download
        return FileResponse(
            path=str(tmp_path),
            filename=f"{daemon_label}_{timestamp[:10] if len(timestamp) >= 10 else 'export'}{ANIMA_EXTENSION}",
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={daemon_label}{ANIMA_EXTENSION}"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Clean up temp file on error
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daemons/import")
async def import_daemon_endpoint(
    file: UploadFile = File(...),
    daemon_name: Optional[str] = Form(None),
    skip_embeddings: bool = Form(False),
    admin: Dict = Depends(require_admin)
):
    """Import a daemon from uploaded .anima file."""
    from daemon_export import import_daemon, ANIMA_EXTENSION

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix if file.filename else ANIMA_EXTENSION
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)

    try:
        result = import_daemon(
            tmp_path,
            new_daemon_name=daemon_name,
            skip_embeddings=skip_embeddings
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/daemons/import/preview")
async def preview_daemon_import_endpoint(
    file: UploadFile = File(...),
    admin: Dict = Depends(require_admin)
):
    """Preview daemon import without applying."""
    from daemon_export import preview_daemon_import, ANIMA_EXTENSION

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix if file.filename else ANIMA_EXTENSION
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)

    try:
        preview = preview_daemon_import(tmp_path)
        return preview
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/daemons/import/seed/{filename}")
async def import_seed_daemon(
    filename: str,
    daemon_name: Optional[str] = None,
    skip_embeddings: bool = False,
    admin: Dict = Depends(require_admin)
):
    """Import a daemon from a seed file by filename.

    Supports both .anima (full export) and .json (genesis) files.
    """
    from daemon_export import import_daemon, import_from_genesis_json, list_seed_exports
    import json

    # Find the seed file
    exports = list_seed_exports()
    seed_file = next((e for e in exports if e["filename"] == filename), None)

    if not seed_file:
        raise HTTPException(status_code=404, detail=f"Seed file '{filename}' not found")

    if "error" in seed_file:
        raise HTTPException(status_code=400, detail=f"Seed file has errors: {seed_file['error']}")

    try:
        file_type = seed_file.get("type", "anima")

        if file_type == "genesis":
            # Import genesis JSON
            with open(seed_file["path"], 'r') as f:
                json_data = json.load(f)
            result = import_from_genesis_json(
                json_data=json_data,
                importing_user_id=admin["user_id"],
                merge_existing=False
            )
        else:
            # Import anima file
            result = import_daemon(
                Path(seed_file["path"]),
                new_daemon_name=daemon_name,
                skip_embeddings=skip_embeddings
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daemons/import/genesis")
async def import_genesis_json(
    request: GenesisJsonImportRequest,
    admin: Dict = Depends(require_admin)
):
    """Import a daemon from Genesis Prompt JSON format."""
    from daemon_export import import_from_genesis_json

    if not admin.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        result = import_from_genesis_json(
            json_data=request.json_data,
            importing_user_id=admin["user_id"],
            merge_existing=request.merge_existing
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daemons/import/genesis/preview")
async def preview_genesis_json_import(
    request: GenesisJsonImportRequest,
    admin: Dict = Depends(require_admin)
):
    """Preview what would be imported from Genesis Prompt JSON."""
    from daemon_export import preview_genesis_json

    if not admin.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        result = preview_genesis_json(request.json_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
