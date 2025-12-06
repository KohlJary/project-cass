"""
File Operations REST API routes
File/directory CRUD operations for the TUI FilesPanel
"""
import os
import shutil
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/files", tags=["files"])


# === Request Models ===

class CreateFileRequest(BaseModel):
    """Request to create a new file"""
    path: str  # Full path including filename
    content: str = ""  # Optional initial content


class CreateDirRequest(BaseModel):
    """Request to create a new directory"""
    path: str  # Full path for the directory


class RenameRequest(BaseModel):
    """Request to rename/move a file or directory"""
    old_path: str
    new_path: str


class DeleteRequest(BaseModel):
    """Request to delete a file or directory"""
    path: str
    recursive: bool = False  # For directories


# === Helper Functions ===

def validate_path(path: str, must_exist: bool = False, must_not_exist: bool = False) -> Path:
    """Validate and return a Path object"""
    p = Path(path)

    # Security: prevent path traversal attacks
    try:
        # Resolve to absolute path
        resolved = p.resolve()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid path: {e}")

    if must_exist and not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Path does not exist: {path}")

    if must_not_exist and resolved.exists():
        raise HTTPException(status_code=409, detail=f"Path already exists: {path}")

    return resolved


def get_parent_dir(path: Path) -> Path:
    """Get parent directory, validating it exists"""
    parent = path.parent
    if not parent.exists():
        raise HTTPException(status_code=400, detail=f"Parent directory does not exist: {parent}")
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail=f"Parent is not a directory: {parent}")
    return parent


# === Endpoints ===

@router.post("/create")
async def create_file(request: CreateFileRequest):
    """Create a new file with optional content"""
    path = validate_path(request.path, must_not_exist=True)
    parent = get_parent_dir(path)

    try:
        path.write_text(request.content)
        return {
            "success": True,
            "path": str(path),
            "size": len(request.content)
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create file: {e}")


@router.post("/mkdir")
async def create_directory(request: CreateDirRequest):
    """Create a new directory"""
    path = validate_path(request.path, must_not_exist=True)

    try:
        # Create directory and any missing parents
        path.mkdir(parents=True, exist_ok=False)
        return {
            "success": True,
            "path": str(path)
        }
    except FileExistsError:
        raise HTTPException(status_code=409, detail="Directory already exists")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create directory: {e}")


@router.post("/rename")
async def rename_path(request: RenameRequest):
    """Rename or move a file or directory"""
    old_path = validate_path(request.old_path, must_exist=True)
    new_path = validate_path(request.new_path, must_not_exist=True)

    # Ensure parent of new path exists
    get_parent_dir(new_path)

    try:
        old_path.rename(new_path)
        return {
            "success": True,
            "old_path": str(old_path),
            "new_path": str(new_path),
            "is_directory": new_path.is_dir()
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename: {e}")


@router.delete("/delete")
async def delete_path(request: DeleteRequest):
    """Delete a file or directory"""
    path = validate_path(request.path, must_exist=True)

    try:
        if path.is_dir():
            if request.recursive:
                shutil.rmtree(path)
            else:
                # Only delete if empty
                try:
                    path.rmdir()
                except OSError:
                    raise HTTPException(
                        status_code=400,
                        detail="Directory not empty. Use recursive=true to delete."
                    )
        else:
            path.unlink()

        return {
            "success": True,
            "path": str(path),
            "was_directory": path.is_dir() if path.exists() else None
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")


@router.get("/read")
async def read_file(path: str, max_size: int = 100 * 1024):
    """Read file contents (with size limit for safety)"""
    file_path = validate_path(path, must_exist=True)

    if file_path.is_dir():
        raise HTTPException(status_code=400, detail="Cannot read a directory")

    # Check file size
    size = file_path.stat().st_size
    if size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size} bytes). Max: {max_size} bytes."
        )

    try:
        content = file_path.read_text()
        return {
            "path": str(file_path),
            "content": content,
            "size": size
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File appears to be binary")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")


@router.get("/list")
async def list_directory(path: str, include_hidden: bool = False):
    """List contents of a directory"""
    dir_path = validate_path(path, must_exist=True)

    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    try:
        entries = []
        for entry in dir_path.iterdir():
            if not include_hidden and entry.name.startswith('.'):
                continue

            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else None,
                "modified": stat.st_mtime
            })

        # Sort: directories first, then files, alphabetically
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        return {
            "path": str(dir_path),
            "entries": entries,
            "count": len(entries)
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list directory: {e}")


@router.get("/exists")
async def check_exists(path: str):
    """Check if a path exists"""
    p = Path(path)
    exists = p.exists()

    return {
        "path": path,
        "exists": exists,
        "is_file": p.is_file() if exists else None,
        "is_dir": p.is_dir() if exists else None
    }
