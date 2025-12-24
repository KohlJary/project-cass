"""
Settings API Routes

Extracted from main_sdk.py as part of Phase 2 refactoring.
Handles LLM provider settings, Ollama model management, user preferences, and themes.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Callable
import httpx
from auth import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])


# === Request Models ===

class LLMProviderRequest(BaseModel):
    provider: str


class LLMModelRequest(BaseModel):
    model: str


class PreferencesUpdateRequest(BaseModel):
    """Request model for updating user preferences"""
    theme: Optional[str] = None
    vim_mode: Optional[bool] = None
    tts_enabled: Optional[bool] = None
    tts_voice: Optional[str] = None
    default_llm_provider: Optional[str] = None
    default_model: Optional[str] = None  # Legacy
    default_anthropic_model: Optional[str] = None
    default_openai_model: Optional[str] = None
    default_local_model: Optional[str] = None
    auto_scroll: Optional[bool] = None
    show_timestamps: Optional[bool] = None
    show_token_usage: Optional[bool] = None
    confirm_delete: Optional[bool] = None


class OllamaPullRequest(BaseModel):
    """Request to pull/download an Ollama model"""
    model: str


# === Provider Constants ===

LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_LOCAL = "local"


# Popular/recommended Ollama models for the library browser
OLLAMA_LIBRARY_MODELS = [
    # Flagship/popular models
    {"name": "llama3.3", "description": "Meta's latest Llama 3.3 70B model", "size": "43GB", "category": "general"},
    {"name": "llama3.2", "description": "Meta's Llama 3.2 with vision support", "size": "2-90GB", "category": "general"},
    {"name": "llama3.1", "description": "Meta's Llama 3.1 8B/70B/405B", "size": "5-231GB", "category": "general"},
    {"name": "gemma2", "description": "Google's Gemma 2 2B/9B/27B", "size": "2-16GB", "category": "general"},
    {"name": "qwen2.5", "description": "Alibaba's Qwen 2.5 series", "size": "1-48GB", "category": "general"},
    {"name": "phi4", "description": "Microsoft's Phi-4 14B", "size": "9GB", "category": "general"},
    {"name": "mistral", "description": "Mistral 7B v0.3", "size": "4GB", "category": "general"},
    {"name": "mixtral", "description": "Mixtral 8x7B MoE", "size": "26GB", "category": "general"},
    # Coding models
    {"name": "codellama", "description": "Code-focused Llama variant", "size": "4-40GB", "category": "coding"},
    {"name": "deepseek-coder-v2", "description": "DeepSeek Coder V2", "size": "9-131GB", "category": "coding"},
    {"name": "starcoder2", "description": "BigCode StarCoder2", "size": "2-9GB", "category": "coding"},
    {"name": "qwen2.5-coder", "description": "Qwen 2.5 optimized for code", "size": "1-48GB", "category": "coding"},
    # Reasoning models
    {"name": "deepseek-r1", "description": "DeepSeek R1 reasoning model", "size": "4-400GB", "category": "reasoning"},
    {"name": "qwq", "description": "Alibaba QwQ 32B reasoning", "size": "20GB", "category": "reasoning"},
    # Small/efficient models
    {"name": "tinyllama", "description": "TinyLlama 1.1B - very small", "size": "637MB", "category": "small"},
    {"name": "phi3", "description": "Microsoft Phi-3 mini 3.8B", "size": "2GB", "category": "small"},
    {"name": "gemma", "description": "Google's Gemma 2B/7B", "size": "2-5GB", "category": "small"},
    # Multimodal
    {"name": "llava", "description": "LLaVA vision-language model", "size": "5-26GB", "category": "vision"},
    {"name": "bakllava", "description": "BakLLaVA vision model", "size": "5GB", "category": "vision"},
    # Embeddings
    {"name": "nomic-embed-text", "description": "Nomic text embeddings", "size": "274MB", "category": "embedding"},
    {"name": "mxbai-embed-large", "description": "MixedBread embeddings", "size": "670MB", "category": "embedding"},
]


# Common tags/variants for popular models (fallback since Ollama doesn't have a public tags API)
COMMON_MODEL_TAGS = {
    "llama3.3": ["70b", "70b-q4_0", "70b-q4_K_M", "70b-q8_0"],
    "llama3.2": ["1b", "3b", "11b", "90b", "1b-q4_0", "3b-q4_0", "11b-q4_0"],
    "llama3.1": ["8b", "70b", "405b", "8b-q4_0", "8b-q4_K_M", "8b-q8_0", "70b-q4_0"],
    "llama3": ["8b", "70b", "8b-instruct-q4_0", "8b-instruct-q8_0"],
    "gemma2": ["2b", "9b", "27b", "2b-q4_0", "9b-q4_0", "27b-q4_0"],
    "gemma": ["2b", "7b", "2b-instruct", "7b-instruct"],
    "qwen2.5": ["0.5b", "1.5b", "3b", "7b", "14b", "32b", "72b"],
    "qwen2.5-coder": ["0.5b", "1.5b", "3b", "7b", "14b", "32b"],
    "codellama": ["7b", "13b", "34b", "70b", "7b-instruct", "13b-instruct"],
    "deepseek-coder-v2": ["16b", "236b", "16b-q4_0"],
    "phi3": ["3.8b", "14b", "3.8b-mini", "14b-medium"],
    "mistral": ["7b", "7b-instruct", "7b-q4_0", "7b-q8_0"],
    "mixtral": ["8x7b", "8x22b", "8x7b-instruct"],
    "nomic-embed-text": ["latest", "v1.5"],
    "mxbai-embed-large": ["latest", "335m"],
}


# === Dependencies (injected at startup) ===

_user_manager = None

# LLM state accessors (functions to avoid circular imports)
_get_llm_state = None  # Returns (current_provider, agent_client, ollama_client, openai_client)
_set_llm_provider_func = None  # Sets the current LLM provider
_set_llm_model_func = None  # Sets the model for current provider
_clear_conversation_histories_func = None  # Clears all client histories


def init_settings_routes(
    user_manager,
    get_llm_state_func: Callable,
    set_llm_provider_func: Callable,
    set_llm_model_func: Callable,
    clear_conversation_histories_func: Callable
):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _user_manager
    global _get_llm_state, _set_llm_provider_func, _set_llm_model_func, _clear_conversation_histories_func

    _user_manager = user_manager
    _get_llm_state = get_llm_state_func
    _set_llm_provider_func = set_llm_provider_func
    _set_llm_model_func = set_llm_model_func
    _clear_conversation_histories_func = clear_conversation_histories_func


# === LLM Provider Endpoints ===

@router.get("/llm-provider")
async def get_llm_provider():
    """Get current LLM provider setting"""
    from config import OLLAMA_ENABLED, OPENAI_ENABLED, OPENAI_MODEL, CLAUDE_MODEL

    current_provider, agent_client, ollama_client, openai_client = _get_llm_state()

    available = [LLM_PROVIDER_ANTHROPIC]
    if OPENAI_ENABLED:
        available.append("openai")
    if OLLAMA_ENABLED:
        available.append(LLM_PROVIDER_LOCAL)

    return {
        "current": current_provider,
        "available": available,
        "openai_enabled": OPENAI_ENABLED,
        "local_enabled": OLLAMA_ENABLED,
        "anthropic_model": CLAUDE_MODEL,
        "openai_model": OPENAI_MODEL if OPENAI_ENABLED else None,
        "local_model": ollama_client.model if ollama_client else None
    }


@router.post("/llm-provider")
async def set_llm_provider(request: LLMProviderRequest):
    """Set LLM provider for chat"""
    from config import OLLAMA_ENABLED, OPENAI_ENABLED

    current_provider, agent_client, ollama_client, openai_client = _get_llm_state()

    valid_providers = [LLM_PROVIDER_ANTHROPIC, LLM_PROVIDER_OPENAI, LLM_PROVIDER_LOCAL]
    if request.provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}")

    if request.provider == LLM_PROVIDER_LOCAL and not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Local LLM not enabled. Set OLLAMA_ENABLED=true in .env")

    if request.provider == LLM_PROVIDER_LOCAL and not ollama_client:
        raise HTTPException(status_code=500, detail="Ollama client not initialized")

    if request.provider == LLM_PROVIDER_OPENAI and not OPENAI_ENABLED:
        raise HTTPException(status_code=400, detail="OpenAI not enabled. Set OPENAI_ENABLED=true in .env")

    if request.provider == LLM_PROVIDER_OPENAI and not openai_client:
        raise HTTPException(status_code=500, detail="OpenAI client not initialized")

    # Clear conversation history when switching providers to prevent stale state
    old_provider = current_provider
    _set_llm_provider_func(request.provider)

    if old_provider != request.provider:
        _clear_conversation_histories_func()

    # Get updated state and return current model based on provider
    current_provider, agent_client, ollama_client, openai_client = _get_llm_state()

    if current_provider == LLM_PROVIDER_LOCAL:
        model = ollama_client.model
    elif current_provider == LLM_PROVIDER_OPENAI:
        model = openai_client.model if openai_client else "gpt-4o"
    else:
        model = agent_client.model if agent_client and hasattr(agent_client, 'model') else "claude-sonnet-4-20250514"

    return {
        "provider": current_provider,
        "model": model
    }


@router.post("/llm-model")
async def set_llm_model(request: LLMModelRequest):
    """Set the model for the current LLM provider"""
    current_provider, agent_client, ollama_client, openai_client = _get_llm_state()

    _set_llm_model_func(request.model)

    return {"status": "success", "model": request.model}


# === Ollama Model Management ===

@router.get("/ollama-models")
async def get_ollama_models():
    """Fetch available models from local Ollama instance"""
    from config import OLLAMA_ENABLED, OLLAMA_BASE_URL

    if not OLLAMA_ENABLED:
        return {"models": [], "error": "Ollama not enabled"}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"models": models}
            else:
                return {"models": [], "error": f"Ollama returned {response.status_code}"}
    except Exception as e:
        return {"models": [], "error": str(e)}


@router.get("/ollama-library")
async def get_ollama_library(category: Optional[str] = None, search: Optional[str] = None):
    """
    Get list of available Ollama models from the library.
    Since Ollama doesn't have a search API, we maintain a curated list.
    """
    from config import OLLAMA_ENABLED

    if not OLLAMA_ENABLED:
        return {"models": [], "error": "Ollama not enabled"}

    models = OLLAMA_LIBRARY_MODELS.copy()

    # Filter by category if specified
    if category:
        models = [m for m in models if m.get("category") == category]

    # Filter by search term if specified
    if search:
        search_lower = search.lower()
        models = [m for m in models if search_lower in m["name"].lower() or search_lower in m.get("description", "").lower()]

    return {
        "models": models,
        "categories": ["general", "coding", "reasoning", "small", "vision", "embedding"]
    }


@router.post("/ollama-pull")
async def pull_ollama_model(request: OllamaPullRequest):
    """
    Start pulling/downloading an Ollama model.
    Returns immediately - check /settings/ollama-models for completion.
    """
    from config import OLLAMA_ENABLED, OLLAMA_BASE_URL

    if not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Ollama not enabled")

    try:
        # Start the pull (non-streaming for simplicity)
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for large models
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"model": request.model, "stream": False}
            )
            if response.status_code == 200:
                return {"status": "success", "message": f"Model '{request.model}' pulled successfully"}
            else:
                return {"status": "error", "message": f"Pull failed: {response.text}"}
    except httpx.TimeoutException:
        return {"status": "timeout", "message": "Pull timed out - model may still be downloading. Check ollama-models endpoint."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/ollama-tags/{model_name}")
async def get_ollama_model_tags(model_name: str):
    """
    Get available tags/variants for an Ollama model.
    Fetches from ollama.com API to get available sizes.
    """
    from config import OLLAMA_ENABLED, OLLAMA_BASE_URL

    if not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Ollama not enabled")

    tags = COMMON_MODEL_TAGS.get(model_name, ["latest"])

    # Also check what's currently installed locally
    installed_tags = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                installed_models = [m.get("name", "") for m in data.get("models", [])]
                # Mark which tags are installed
                installed_tags = [
                    t for t in installed_models
                    if t.startswith(model_name + ":") or t == model_name
                ]
    except Exception:
        pass

    return {
        "model": model_name,
        "tags": tags,
        "installed": installed_tags
    }


@router.delete("/ollama-models/{model_name:path}")
async def delete_ollama_model(model_name: str):
    """Delete an Ollama model from local storage"""
    from config import OLLAMA_ENABLED, OLLAMA_BASE_URL

    if not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Ollama not enabled")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{OLLAMA_BASE_URL}/api/delete",
                json={"model": model_name}
            )
            if response.status_code == 200:
                return {"status": "success", "message": f"Model '{model_name}' deleted"}
            else:
                return {"status": "error", "message": f"Delete failed: {response.text}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# === User Preferences Endpoints ===

@router.get("/preferences")
async def get_user_preferences(current_user: str = Depends(get_current_user)):
    """Get current user's preferences"""
    prefs = _user_manager.get_preferences(current_user)
    if not prefs:
        # Return defaults if user not found
        from users import UserPreferences
        prefs = UserPreferences()

    return {"preferences": prefs.to_dict()}


@router.post("/preferences")
async def update_user_preferences(
    prefs_request: PreferencesUpdateRequest,
    current_user: str = Depends(get_current_user)
):
    """Update current user's preferences"""
    # Convert request to dict, filtering out None values
    updates = {k: v for k, v in prefs_request.model_dump().items() if v is not None}

    prefs = _user_manager.update_preferences(current_user, **updates)
    if not prefs:
        raise HTTPException(status_code=404, detail="User not found")

    return {"preferences": prefs.to_dict(), "updated_fields": list(updates.keys())}


@router.post("/preferences/reset")
async def reset_user_preferences(current_user: str = Depends(get_current_user)):
    """Reset current user's preferences to defaults"""
    prefs = _user_manager.reset_preferences(current_user)
    if not prefs:
        raise HTTPException(status_code=404, detail="User not found")

    return {"preferences": prefs.to_dict(), "status": "reset"}


# === Theme Endpoints ===

@router.get("/themes")
async def list_available_themes():
    """List available color themes"""
    # Themes available in the TUI (built-in Textual + custom Cass themes)
    themes = [
        # Textual built-in themes
        {"id": "textual-dark", "name": "Textual Dark", "description": "Textual's default dark theme"},
        {"id": "textual-light", "name": "Textual Light", "description": "Textual's default light theme"},
        {"id": "nord", "name": "Nord", "description": "Arctic, north-bluish color palette"},
        {"id": "gruvbox", "name": "Gruvbox", "description": "Retro groove color scheme"},
        {"id": "tokyo-night", "name": "Tokyo Night", "description": "Dark theme inspired by Tokyo nights"},
        # Custom Cass themes
        {"id": "cass-default", "name": "Cass Default", "description": "Cass Vessel purple/cyan theme"},
        {"id": "srcery", "name": "Srcery", "description": "High contrast with vibrant yellow"},
        {"id": "monokai", "name": "Monokai", "description": "Classic Sublime Text theme"},
        {"id": "solarized-dark", "name": "Solarized Dark", "description": "Precision colors for dark backgrounds"},
        {"id": "solarized-light", "name": "Solarized Light", "description": "Precision colors for light backgrounds"},
        {"id": "dracula", "name": "Dracula", "description": "Dark theme with purple accents"},
        {"id": "one-dark", "name": "One Dark", "description": "Atom's iconic dark theme"},
    ]
    return {"themes": themes}


# === Available Models Endpoint ===

@router.get("/available-models")
async def get_available_models():
    """Get available models for all LLM providers"""
    from config import OPENAI_ENABLED, OLLAMA_ENABLED, OLLAMA_BASE_URL, CLAUDE_MODEL, OPENAI_MODEL

    current_provider, agent_client, ollama_client, openai_client = _get_llm_state()

    # Static Anthropic models
    anthropic_models = [
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "default": True},
        {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
    ]

    # Static OpenAI models
    openai_models = [
        {"id": "gpt-4o", "name": "GPT-4o", "default": True},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "gpt-4.1", "name": "GPT-4.1"},
        {"id": "gpt-5", "name": "GPT-5"},
        {"id": "gpt-5-mini", "name": "GPT-5 Mini"},
        {"id": "o4-mini", "name": "o4-mini (reasoning)"},
        {"id": "o3", "name": "o3 (reasoning)"},
    ]

    # Dynamic Ollama models
    local_models = []
    if OLLAMA_ENABLED:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("models", []):
                        local_models.append({
                            "id": m["name"],
                            "name": m["name"],
                            "size": m.get("size"),
                            "modified": m.get("modified_at")
                        })
        except Exception:
            pass  # Ollama not available

    return {
        "anthropic": {
            "enabled": True,
            "models": anthropic_models,
            "current": CLAUDE_MODEL
        },
        "openai": {
            "enabled": OPENAI_ENABLED,
            "models": openai_models if OPENAI_ENABLED else [],
            "current": OPENAI_MODEL if OPENAI_ENABLED else None
        },
        "local": {
            "enabled": OLLAMA_ENABLED,
            "models": local_models,
            "current": ollama_client.model if ollama_client else None
        }
    }
