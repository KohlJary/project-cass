"""
Projects API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles project CRUD, files, documents, and GitHub metrics.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/projects", tags=["projects"])


# === Request Models ===

class ProjectCreateRequest(BaseModel):
    name: str
    working_directory: str
    description: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    working_directory: Optional[str] = None
    description: Optional[str] = None
    github_repo: Optional[str] = None  # "owner/repo" format
    github_token: Optional[str] = None  # Per-project PAT
    clear_github_token: Optional[bool] = None  # Set True to remove project token


class ProjectAddFileRequest(BaseModel):
    file_path: str
    description: Optional[str] = None
    embed: bool = True  # Whether to embed the file immediately


class ProjectDocumentCreateRequest(BaseModel):
    title: str
    content: str
    created_by: str = "cass"  # "cass" or "user"
    embed: bool = True  # Whether to embed immediately


class ProjectDocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    embed: bool = True  # Whether to re-embed after update


# === Dependencies (injected at startup) ===

_project_manager = None
_memory = None
_conversation_manager = None
_github_metrics_manager = None


def init_projects_routes(project_manager, memory, conversation_manager, github_metrics_manager):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _project_manager, _memory, _conversation_manager, _github_metrics_manager
    _project_manager = project_manager
    _memory = memory
    _conversation_manager = conversation_manager
    _github_metrics_manager = github_metrics_manager


# === Project CRUD ===

@router.post("/new")
async def create_project(request: ProjectCreateRequest):
    """Create a new project"""
    try:
        project = _project_manager.create_project(
            name=request.name,
            working_directory=request.working_directory,
            description=request.description
        )
        return {
            "id": project.id,
            "name": project.name,
            "working_directory": project.working_directory,
            "created_at": project.created_at,
            "file_count": 0
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_projects():
    """List all projects"""
    projects = _project_manager.list_projects()
    return {"projects": projects, "count": len(projects)}


@router.get("/{project_id}")
async def get_project(project_id: str):
    """Get a specific project with file list"""
    project = _project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.to_dict()


@router.put("/{project_id}")
async def update_project(project_id: str, request: ProjectUpdateRequest):
    """Update project details"""
    project = _project_manager.update_project(
        project_id,
        name=request.name,
        working_directory=request.working_directory,
        description=request.description,
        github_repo=request.github_repo,
        github_token=request.github_token,
        clear_github_token=request.clear_github_token or False,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.to_dict()


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and its embeddings"""
    # Remove all embeddings for this project
    removed = _memory.remove_project_embeddings(project_id)

    # Delete the project
    success = _project_manager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "status": "deleted",
        "id": project_id,
        "embeddings_removed": removed
    }


# === Project Conversations ===

@router.get("/{project_id}/conversations")
async def get_project_conversations(project_id: str, limit: Optional[int] = None):
    """Get all conversations for a project"""
    conversations = _conversation_manager.list_by_project(project_id, limit=limit)
    return {"conversations": conversations, "count": len(conversations)}


# === Project Files ===

@router.post("/{project_id}/files")
async def add_project_file(project_id: str, request: ProjectAddFileRequest):
    """Add a file to a project"""
    try:
        project_file = _project_manager.add_file(
            project_id,
            request.file_path,
            request.description
        )
        if not project_file:
            raise HTTPException(status_code=404, detail="Project not found")

        chunks_embedded = 0
        if request.embed:
            # Embed the file
            chunks_embedded = _memory.embed_project_file(
                project_id,
                project_file.path,
                request.description
            )
            # Mark as embedded
            _project_manager.mark_file_embedded(project_id, project_file.path)

        return {
            "status": "added",
            "file_path": project_file.path,
            "embedded": request.embed,
            "chunks": chunks_embedded
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{project_id}/files")
async def remove_project_file(project_id: str, file_path: str):
    """Remove a file from a project"""
    # Remove embeddings first
    removed = _memory.remove_project_file_embeddings(project_id, file_path)

    # Remove from project
    success = _project_manager.remove_file(project_id, file_path)
    if not success:
        raise HTTPException(status_code=404, detail="Project or file not found")

    return {
        "status": "removed",
        "file_path": file_path,
        "embeddings_removed": removed
    }


@router.get("/{project_id}/files")
async def list_project_files(project_id: str):
    """List all files in a project"""
    project = _project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    files = [
        {
            "path": f.path,
            "description": f.description,
            "added_at": f.added_at,
            "embedded": f.embedded
        }
        for f in project.files
    ]
    return {"files": files, "count": len(files)}


@router.post("/{project_id}/embed")
async def embed_project_files(project_id: str):
    """Embed all unembedded files in a project"""
    unembedded = _project_manager.get_unembedded_files(project_id)
    if not unembedded:
        return {"status": "no_files", "message": "No unembedded files found"}

    total_chunks = 0
    embedded_files = []

    for pf in unembedded:
        try:
            chunks = _memory.embed_project_file(
                project_id,
                pf.path,
                pf.description
            )
            _project_manager.mark_file_embedded(project_id, pf.path)
            total_chunks += chunks
            embedded_files.append(pf.path)
        except Exception as e:
            # Log but continue with other files
            print(f"Error embedding {pf.path}: {e}")

    return {
        "status": "embedded",
        "files_embedded": len(embedded_files),
        "total_chunks": total_chunks,
        "files": embedded_files
    }


# === Project Documents ===

@router.post("/{project_id}/documents")
async def create_project_document(project_id: str, request: ProjectDocumentCreateRequest):
    """Create a new document in a project"""
    document = _project_manager.add_document(
        project_id=project_id,
        title=request.title,
        content=request.content,
        created_by=request.created_by
    )

    if not document:
        raise HTTPException(status_code=404, detail="Project not found")

    chunks_embedded = 0
    if request.embed:
        chunks_embedded = _memory.embed_project_document(
            project_id=project_id,
            document_id=document.id,
            title=document.title,
            content=document.content
        )
        _project_manager.mark_document_embedded(project_id, document.id)

    return {
        "status": "created",
        "document": {
            "id": document.id,
            "title": document.title,
            "created_at": document.created_at,
            "created_by": document.created_by,
            "embedded": request.embed,
            "chunks": chunks_embedded
        }
    }


@router.get("/{project_id}/documents")
async def list_project_documents(project_id: str):
    """List all documents in a project"""
    project = _project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    documents = [
        {
            "id": d.id,
            "title": d.title,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
            "created_by": d.created_by,
            "embedded": d.embedded,
            "content_preview": d.content[:200] + "..." if len(d.content) > 200 else d.content
        }
        for d in project.documents
    ]
    return {"documents": documents, "count": len(documents)}


@router.get("/{project_id}/documents/{document_id}")
async def get_project_document(project_id: str, document_id: str):
    """Get a specific document with full content"""
    document = _project_manager.get_document(project_id, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": document.id,
        "title": document.title,
        "content": document.content,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "created_by": document.created_by,
        "embedded": document.embedded
    }


@router.put("/{project_id}/documents/{document_id}")
async def update_project_document(
    project_id: str,
    document_id: str,
    request: ProjectDocumentUpdateRequest
):
    """Update a document"""
    document = _project_manager.update_document(
        project_id=project_id,
        document_id=document_id,
        title=request.title,
        content=request.content
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks_embedded = 0
    if request.embed and request.content is not None:
        # Remove old embeddings and re-embed
        _memory.remove_project_document_embeddings(project_id, document_id)
        chunks_embedded = _memory.embed_project_document(
            project_id=project_id,
            document_id=document_id,
            title=document.title,
            content=document.content
        )
        _project_manager.mark_document_embedded(project_id, document_id)

    return {
        "status": "updated",
        "document": {
            "id": document.id,
            "title": document.title,
            "updated_at": document.updated_at,
            "embedded": document.embedded,
            "chunks": chunks_embedded
        }
    }


@router.delete("/{project_id}/documents/{document_id}")
async def delete_project_document(project_id: str, document_id: str):
    """Delete a document and its embeddings"""
    # Remove embeddings first
    removed = _memory.remove_project_document_embeddings(project_id, document_id)

    # Delete the document
    success = _project_manager.delete_document(project_id, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "status": "deleted",
        "id": document_id,
        "embeddings_removed": removed
    }


@router.get("/{project_id}/documents/search/{query}")
async def search_project_documents(project_id: str, query: str, limit: int = 10):
    """Search documents in a project by semantic similarity"""
    project = _project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    results = _memory.search_project_documents(
        query=query,
        project_id=project_id,
        n_results=limit
    )

    return {
        "query": query,
        "results": results,
        "count": len(results)
    }


@router.post("/{project_id}/documents/embed")
async def embed_project_documents(project_id: str):
    """Embed all unembedded documents in a project"""
    unembedded = _project_manager.get_unembedded_documents(project_id)
    if not unembedded:
        return {"status": "no_documents", "message": "No unembedded documents found"}

    total_chunks = 0
    embedded_docs = []

    for doc in unembedded:
        try:
            chunks = _memory.embed_project_document(
                project_id=project_id,
                document_id=doc.id,
                title=doc.title,
                content=doc.content
            )
            _project_manager.mark_document_embedded(project_id, doc.id)
            total_chunks += chunks
            embedded_docs.append({"id": doc.id, "title": doc.title})
        except Exception as e:
            print(f"Error embedding document {doc.id}: {e}")

    return {
        "status": "embedded",
        "documents_embedded": len(embedded_docs),
        "total_chunks": total_chunks,
        "documents": embedded_docs
    }


# === Project GitHub Metrics ===

@router.get("/{project_id}/github/metrics")
async def get_project_github_metrics(project_id: str):
    """
    Get GitHub metrics for a project's configured repository.

    Uses the project's github_repo and optionally its github_token.
    Falls back to system default token if project token not set.
    """
    project = _project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_repo:
        return {
            "configured": False,
            "message": "No GitHub repository configured for this project",
            "metrics": None
        }

    metrics = await _github_metrics_manager.fetch_project_metrics(
        github_repo=project.github_repo,
        github_token=project.github_token  # None means use system default
    )

    if metrics is None:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch metrics for {project.github_repo}"
        )

    return {
        "configured": True,
        "github_repo": project.github_repo,
        "has_project_token": project.github_token is not None,
        "metrics": metrics
    }


@router.post("/{project_id}/github/refresh")
async def refresh_project_github_metrics(project_id: str):
    """Force refresh GitHub metrics for a project."""
    project = _project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_repo:
        raise HTTPException(
            status_code=400,
            detail="No GitHub repository configured for this project"
        )

    metrics = await _github_metrics_manager.fetch_project_metrics(
        github_repo=project.github_repo,
        github_token=project.github_token
    )

    if metrics is None:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to refresh metrics for {project.github_repo}"
        )

    return {
        "status": "refreshed",
        "github_repo": project.github_repo,
        "metrics": metrics
    }
