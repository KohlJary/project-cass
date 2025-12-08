"""
Cass Vessel - Route Modules
FastAPI APIRouter modules for different endpoint groups
"""
from .tasks import router as tasks_router
from .calendar import router as calendar_router
from .roadmap import router as roadmap_router
from .git import router as git_router
from .files import router as files_router
from .wiki import router as wiki_router
from .export import router as export_router

__all__ = [
    "tasks_router",
    "calendar_router",
    "roadmap_router",
    "git_router",
    "files_router",
    "wiki_router",
    "export_router",
]
