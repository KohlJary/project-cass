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
from .projects import router as projects_router, init_projects_routes
from .journals import router as journals_router, init_journal_routes
from .dreams import router as dreams_router, init_dream_routes
from .solo_reflection import router as solo_reflection_router, init_solo_reflection_routes
from .autonomous_research import router as autonomous_research_router, init_autonomous_research_routes
from .interviews import router as interviews_router, init_interview_routes
from .tts import router as tts_router, init_tts_routes
from .attachments import router as attachments_router, init_attachment_routes

__all__ = [
    "tasks_router",
    "calendar_router",
    "roadmap_router",
    "git_router",
    "files_router",
    "wiki_router",
    "export_router",
    "projects_router",
    "init_projects_routes",
    "journals_router",
    "init_journal_routes",
    "dreams_router",
    "init_dream_routes",
    "solo_reflection_router",
    "init_solo_reflection_routes",
    "autonomous_research_router",
    "init_autonomous_research_routes",
    "interviews_router",
    "init_interview_routes",
    "tts_router",
    "init_tts_routes",
    "attachments_router",
    "init_attachment_routes",
]
