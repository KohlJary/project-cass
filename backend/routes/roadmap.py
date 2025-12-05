"""
Roadmap REST API routes
Work item and milestone management endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/roadmap", tags=["roadmap"])

# Set by main app
_roadmap_manager = None


def init_roadmap_routes(roadmap_manager):
    """Initialize the routes with dependencies"""
    global _roadmap_manager
    _roadmap_manager = roadmap_manager


# === Request Models ===

class CreateItemRequest(BaseModel):
    title: str
    description: str = ""
    status: str = "backlog"
    priority: str = "P2"
    item_type: str = "feature"
    tags: List[str] = []
    assigned_to: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None
    source_conversation_id: Optional[str] = None
    created_by: str = "user"


class UpdateItemRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    item_type: Optional[str] = None
    tags: Optional[List[str]] = None
    assigned_to: Optional[str] = None
    project_id: Optional[str] = None
    milestone_id: Optional[str] = None


class PickItemRequest(BaseModel):
    assigned_to: str


class CreateMilestoneRequest(BaseModel):
    title: str
    description: str = ""
    target_date: Optional[str] = None


class UpdateMilestoneRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[str] = None
    status: Optional[str] = None


class AddLinkRequest(BaseModel):
    target_id: str
    link_type: str  # related, depends_on, blocks, parent, child


class RemoveLinkRequest(BaseModel):
    target_id: str
    link_type: str


# === Work Item Endpoints ===

@router.get("/items")
async def list_items(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    item_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    project_id: Optional[str] = None,
    milestone_id: Optional[str] = None,
    include_archived: bool = False,
):
    """List work items with optional filters"""
    items = _roadmap_manager.list_items(
        status=status,
        priority=priority,
        item_type=item_type,
        assigned_to=assigned_to,
        project_id=project_id,
        milestone_id=milestone_id,
        include_archived=include_archived,
    )
    return {"items": items}


@router.post("/items")
async def create_item(request: CreateItemRequest):
    """Create a new work item"""
    item = _roadmap_manager.create_item(
        title=request.title,
        description=request.description,
        status=request.status,
        priority=request.priority,
        item_type=request.item_type,
        tags=request.tags,
        assigned_to=request.assigned_to,
        project_id=request.project_id,
        milestone_id=request.milestone_id,
        source_conversation_id=request.source_conversation_id,
        created_by=request.created_by,
    )
    return {"item": item.to_dict()}


@router.get("/items/{item_id}")
async def get_item(item_id: str):
    """Get a specific work item"""
    item = _roadmap_manager.load_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item.to_dict()


@router.put("/items/{item_id}")
async def update_item(item_id: str, request: UpdateItemRequest):
    """Update a work item"""
    item = _roadmap_manager.update_item(
        item_id=item_id,
        title=request.title,
        description=request.description,
        status=request.status,
        priority=request.priority,
        item_type=request.item_type,
        tags=request.tags,
        assigned_to=request.assigned_to,
        project_id=request.project_id,
        milestone_id=request.milestone_id,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": item.to_dict()}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str):
    """Delete a work item"""
    _roadmap_manager.delete_item(item_id)
    return {"status": "deleted"}


@router.post("/items/{item_id}/pick")
async def pick_item(item_id: str, request: PickItemRequest):
    """Claim an item for work"""
    item = _roadmap_manager.pick_item(item_id, request.assigned_to)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": item.to_dict()}


@router.post("/items/{item_id}/complete")
async def complete_item(item_id: str):
    """Mark an item as done"""
    item = _roadmap_manager.complete_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": item.to_dict()}


@router.post("/items/{item_id}/advance")
async def advance_item(item_id: str, force: bool = False):
    """Move item to next status in workflow"""
    result = _roadmap_manager.advance_status(item_id, force=force)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    response = {}
    if result.get("item"):
        response["item"] = result["item"].to_dict()
    if result.get("warning"):
        response["warning"] = result["warning"]
    return response


# === Link Endpoints ===

@router.post("/items/{item_id}/links")
async def add_link(item_id: str, request: AddLinkRequest):
    """Add a link to another item"""
    item = _roadmap_manager.add_link(
        source_id=item_id,
        target_id=request.target_id,
        link_type=request.link_type,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": item.to_dict()}


@router.delete("/items/{item_id}/links")
async def remove_link(item_id: str, request: RemoveLinkRequest):
    """Remove a link to another item"""
    item = _roadmap_manager.remove_link(
        source_id=item_id,
        target_id=request.target_id,
        link_type=request.link_type,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"item": item.to_dict()}


@router.get("/items/{item_id}/links")
async def get_links(item_id: str):
    """Get all links for an item with resolved details"""
    result = _roadmap_manager.get_item_links(item_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/items/{item_id}/dependencies")
async def check_dependencies(item_id: str):
    """Check if an item has unmet dependencies"""
    result = _roadmap_manager.check_dependencies(item_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# === Milestone Endpoints ===

@router.get("/milestones")
async def list_milestones(include_archived: bool = False):
    """List all milestones"""
    milestones = _roadmap_manager.list_milestones(include_archived=include_archived)
    return {"milestones": milestones}


@router.post("/milestones")
async def create_milestone(request: CreateMilestoneRequest):
    """Create a new milestone"""
    milestone = _roadmap_manager.create_milestone(
        title=request.title,
        description=request.description,
        target_date=request.target_date,
    )
    return {"milestone": milestone.to_dict()}


@router.put("/milestones/{milestone_id}")
async def update_milestone(milestone_id: str, request: UpdateMilestoneRequest):
    """Update a milestone"""
    milestone = _roadmap_manager.update_milestone(
        milestone_id=milestone_id,
        title=request.title,
        description=request.description,
        target_date=request.target_date,
        status=request.status,
    )
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"milestone": milestone.to_dict()}


@router.get("/milestones/{milestone_id}/progress")
async def milestone_progress(milestone_id: str):
    """Get progress stats for a milestone"""
    progress = _roadmap_manager.get_milestone_progress(milestone_id)
    return progress
