"""
Interview System API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles interview protocols, responses, and model comparisons.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/interviews", tags=["interviews"])


# === Request Models ===

class RunInterviewRequest(BaseModel):
    protocol_id: str
    models: Optional[List[str]] = None  # Model names to run, None = all defaults


class AnnotationRequest(BaseModel):
    prompt_id: str
    start_offset: int
    end_offset: int
    highlighted_text: str
    note: str
    annotation_type: str = "observation"


# === Dependencies (injected at startup) ===

_protocol_manager = None
_storage = None
_default_models = None
_anthropic_api_key = None
_openai_api_key = None
_ollama_base_url = None


def init_interview_routes(
    protocol_manager,
    storage,
    default_models,
    anthropic_api_key: str,
    openai_api_key: str,
    ollama_base_url: str
):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _protocol_manager, _storage, _default_models
    global _anthropic_api_key, _openai_api_key, _ollama_base_url
    _protocol_manager = protocol_manager
    _storage = storage
    _default_models = default_models
    _anthropic_api_key = anthropic_api_key
    _openai_api_key = openai_api_key
    _ollama_base_url = ollama_base_url


# === Interview Endpoints ===

@router.get("/protocols")
async def list_interview_protocols():
    """List all available interview protocols."""
    protocols = _protocol_manager.list_all()
    return {
        "protocols": [p.to_dict() for p in protocols]
    }


@router.get("/protocols/{protocol_id}")
async def get_interview_protocol(protocol_id: str):
    """Get a specific interview protocol."""
    protocol = _protocol_manager.load(protocol_id)
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return protocol.to_dict()


@router.post("/run")
async def run_interview(request: RunInterviewRequest):
    """
    Run an interview protocol across multiple models.

    This is async and may take a while depending on model response times.
    """
    from interviews import InterviewDispatcher

    protocol = _protocol_manager.load(request.protocol_id)
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    # Filter models if specified
    if request.models:
        model_configs = [m for m in _default_models if m.name in request.models]
    else:
        model_configs = _default_models

    if not model_configs:
        raise HTTPException(status_code=400, detail="No valid models specified")

    # Create dispatcher with API keys
    dispatcher = InterviewDispatcher(
        anthropic_api_key=_anthropic_api_key,
        openai_api_key=_openai_api_key,
        ollama_base_url=_ollama_base_url
    )

    # Run interviews
    results = await dispatcher.run_interview_batch(protocol, model_configs)

    # Save responses
    response_ids = _storage.save_batch(results)

    return {
        "protocol_id": protocol.id,
        "models_run": [r["model_name"] for r in results],
        "response_ids": response_ids,
        "errors": [r.get("error") for r in results if r.get("error")]
    }


@router.get("/responses")
async def list_interview_responses(
    protocol_id: Optional[str] = None,
    model_name: Optional[str] = None
):
    """List interview responses, optionally filtered."""
    responses = _storage.list_responses(
        protocol_id=protocol_id,
        model_name=model_name
    )
    return {
        "responses": [r.to_dict() for r in responses]
    }


@router.get("/responses/{response_id}")
async def get_interview_response(response_id: str):
    """Get a specific interview response with annotations."""
    response = _storage.load_response(response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    annotations = _storage.get_annotations(response_id)

    return {
        **response.to_dict(),
        "annotations": [a.to_dict() for a in annotations]
    }


@router.get("/compare/{protocol_id}/{prompt_id}")
async def compare_responses(protocol_id: str, prompt_id: str):
    """Get side-by-side comparison of all model responses to a specific prompt."""
    comparison = _storage.get_side_by_side(protocol_id, prompt_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="No responses found")

    return {
        "protocol_id": protocol_id,
        "prompt_id": prompt_id,
        "responses": comparison
    }


@router.post("/responses/{response_id}/annotations")
async def add_annotation(response_id: str, request: AnnotationRequest):
    """Add an annotation to a response."""
    response = _storage.load_response(response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    annotation = _storage.add_annotation(
        response_id=response_id,
        prompt_id=request.prompt_id,
        start_offset=request.start_offset,
        end_offset=request.end_offset,
        highlighted_text=request.highlighted_text,
        note=request.note,
        annotation_type=request.annotation_type
    )

    return annotation.to_dict()


@router.delete("/responses/{response_id}/annotations/{annotation_id}")
async def delete_annotation(response_id: str, annotation_id: str):
    """Delete an annotation."""
    success = _storage.delete_annotation(response_id, annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"deleted": True}


@router.get("/models")
async def list_available_models():
    """List available models for interviews."""
    return {
        "models": [
            {
                "name": m.name,
                "provider": m.provider,
                "model_id": m.model_id
            }
            for m in _default_models
        ]
    }
