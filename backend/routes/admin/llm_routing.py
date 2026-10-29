"""
Admin API - per-subsystem LLM model routing (#64).

Every LLM call site is registered in llm_config.CALL_SITES with a default (the
model it ran before routing). These routes let an admin override the model for
a call site, clear the override, and see each call site's calls and spend from
the token ledger (token_usage_records.call_site).

All routes are under /admin and require an admin (route_guard is default-deny
for /admin; each handler also declares require_admin).
"""
import os
from typing import Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from llm_config import (
    AVAILABLE_MODELS,
    CALL_SITE_METADATA,
    CALL_SITES,
    LLMConfigManager,
    ModelAssignment,
    PinnedCallSite,
    UnknownCallSite,
)
from .auth import require_admin

router = APIRouter(tags=["admin-llm-config"])

PROVIDERS = {"anthropic", "ollama", "openai"}


def _usage(days: int) -> Dict[str, Dict]:
    try:
        from token_tracker import TokenUsageTracker
        return TokenUsageTracker().get_call_site_summary(days=days)
    except Exception as e:  # ledger unavailable: show config without usage
        from strict import report_swallowed
        report_swallowed(e, "llm-config usage summary")
        return {}


def _failures(days: int) -> Dict[str, Dict]:
    try:
        from token_tracker import TokenUsageTracker
        return TokenUsageTracker().get_failure_summary(days=days)
    except Exception as e:  # failure table unavailable: show usage without it
        from strict import report_swallowed
        report_swallowed(e, "llm-config failure summary")
        return {}


def _with_failures(usage: Dict[str, Dict], failures: Dict[str, Dict]) -> Dict[str, Dict]:
    """Each site's usage plus its failed attempts and failure rate.

    failure_rate is failed attempts over all attempts. Answered calls are in
    `calls`; a rejected reply has a ledger row too, so it isn't counted twice.
    """
    empty = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
             "last_call": None, "models": []}
    out = {}
    for name in set(usage) | set(failures):
        u = dict(usage.get(name) or empty)
        f = failures.get(name)
        u["failures"] = f or {"failures": 0, "lost": 0, "rejected": 0}
        attempts = u["calls"] + (f["failures"] - f["rejected"] if f else 0)
        u["failure_rate"] = round(f["failures"] / attempts, 4) if f and attempts else 0.0
        out[name] = u
    return out


def _site_view(manager: LLMConfigManager, name: str, usage: Dict[str, Dict]) -> Dict:
    site = CALL_SITES[name]
    try:
        default = site.default()
    except Exception:
        default = None
    override = manager.override_for(name)
    effective = manager.resolve(name)
    return {
        "call_site": name,
        "metadata": CALL_SITE_METADATA.get(name, {}),
        "default": default.to_dict() if default else None,
        "default_note": getattr(site.default, "describe", ""),
        "default_from_caller": bool(getattr(site.default, "from_caller", False)),
        "override": override.to_dict() if override and not site.pinned else None,
        "effective": effective.to_dict() if effective else None,
        "pinned": site.pinned,
        "pinned_reason": site.pinned_reason,
        "text_only": site.text_only,
        "usage": usage.get(name, {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                  "cost_usd": 0.0, "last_call": None, "models": []}),
    }


def _available_models(manager: LLMConfigManager) -> list:
    """AVAILABLE_MODELS plus any model a call site uses that the list lacks."""
    models = [dict(m) for m in AVAILABLE_MODELS]
    seen = {(m["provider"], m["model_id"]) for m in models}
    for name in CALL_SITES:
        a = manager.resolve(name)
        if a is None:
            continue
        for provider, model_id in ((a.provider, a.model_id), (a.fallback_provider, a.fallback_model_id)):
            if provider and model_id and (provider, model_id) not in seen:
                seen.add((provider, model_id))
                models.append({"provider": provider, "model_id": model_id, "name": model_id,
                               "local": provider == "ollama"})
    return models


@router.get("/llm-config")
async def get_llm_config(
    days: int = Query(30, ge=1, le=365),
    admin: Dict = Depends(require_admin),
):
    """Every call site: default, override, effective model, and usage over `days`."""
    manager = LLMConfigManager()
    usage = _with_failures(_usage(days), _failures(days))
    sites = [_site_view(manager, name, usage) for name in sorted(CALL_SITES)]
    # Back-compat shape for older clients: effective assignment + metadata.
    assignments = {
        s["call_site"]: {**(s["effective"] or {"provider": "none", "model_id": "",
                                               "fallback_provider": None, "fallback_model_id": None}),
                         "metadata": s["metadata"]}
        for s in sites
    }
    other_usage = {k: v for k, v in usage.items() if k not in CALL_SITES}
    return {
        "days": days,
        "call_sites": sites,
        "other_usage": other_usage,
        "assignments": assignments,
        "available_models": _available_models(manager),
        "call_site_metadata": CALL_SITE_METADATA,
    }


@router.get("/llm-config/usage")
async def get_llm_usage(
    days: int = Query(30, ge=1, le=365),
    admin: Dict = Depends(require_admin),
):
    """Calls, tokens, spend and failed attempts per call site."""
    return {"days": days, "usage": _with_failures(_usage(days), _failures(days))}


@router.put("/llm-config/{call_site}")
async def set_llm_config(call_site: str, body: dict, admin: Dict = Depends(require_admin)):
    """Override the model for one call site."""
    provider = body.get("provider")
    model_id = body.get("model_id")
    if provider not in PROVIDERS or not model_id:
        raise HTTPException(status_code=400, detail=f"provider must be one of {sorted(PROVIDERS)} and model_id set")
    fb_provider = body.get("fallback_provider") or None
    fb_model = body.get("fallback_model_id") or None
    if (fb_provider is None) != (fb_model is None) or (fb_provider and fb_provider not in PROVIDERS):
        raise HTTPException(status_code=400, detail="fallback needs both a valid provider and a model_id")
    assignment = ModelAssignment(provider=provider, model_id=model_id,
                                 fallback_provider=fb_provider, fallback_model_id=fb_model)
    try:
        LLMConfigManager().set(call_site, assignment)
    except UnknownCallSite:
        raise HTTPException(status_code=404, detail=f"Unknown call site: {call_site}")
    except PinnedCallSite as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "ok", "call_site": call_site, "assignment": assignment.to_dict()}


@router.delete("/llm-config/{call_site}")
async def clear_llm_config(call_site: str, admin: Dict = Depends(require_admin)):
    """Remove the override: the call site goes back to its default model."""
    if call_site not in CALL_SITES:
        raise HTTPException(status_code=404, detail=f"Unknown call site: {call_site}")
    LLMConfigManager().clear(call_site)
    return {"status": "ok", "call_site": call_site}


@router.post("/llm-config/reset")
async def reset_llm_config(admin: Dict = Depends(require_admin)):
    """Remove every override."""
    LLMConfigManager().reset_to_defaults()
    return {"status": "ok", "message": "Reset to defaults"}


@router.get("/llm-config/models")
async def get_available_models(admin: Dict = Depends(require_admin)):
    """Models to choose from, marking which Ollama models are installed."""
    installed_ollama = set()
    try:
        base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{base}/api/tags")
        if response.status_code == 200:
            for model in response.json().get("models", []):
                installed_ollama.add(model.get("name", ""))
    except Exception:
        pass

    models = []
    for model in _available_models(LLMConfigManager()):
        info = dict(model)
        if model["provider"] == "ollama":
            info["installed"] = any(
                model["model_id"] in name or model["model_id"].split(":")[0] in name
                for name in installed_ollama
            )
        else:
            info["installed"] = True
        models.append(info)
    return {"models": models}
