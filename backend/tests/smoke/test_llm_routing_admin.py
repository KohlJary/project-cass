"""
Admin model routing (#64) through the booted app: the /admin/llm-config routes
are admin-only, an admin can set a subsystem to an Ollama model and the next
call uses it, and each call site's calls and spend come back from the ledger.
"""
import asyncio

import llm_caller


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_llm_config_routes_are_admin_only(booted_app, smoke_user):
    _, user_token = smoke_user
    for method, path in (("get", "/admin/llm-config"), ("get", "/admin/llm-config/usage"),
                         ("put", "/admin/llm-config/title_generation"),
                         ("delete", "/admin/llm-config/title_generation"),
                         ("post", "/admin/llm-config/reset")):
        kwargs = {"json": {"provider": "ollama", "model_id": "x"}} if method == "put" else {}
        assert getattr(booted_app, method)(path, **kwargs).status_code == 401
        denied = getattr(booted_app, method)(path, headers=_auth(user_token), **kwargs)
        assert denied.status_code in (401, 403), (method, path)


def test_admin_sets_a_subsystem_to_ollama_and_sees_its_spend(booted_app, smoke_admin, fake_llm, monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    _, token = smoke_admin
    body = booted_app.get("/admin/llm-config", headers=_auth(token)).json()
    sites = {s["call_site"]: s for s in body["call_sites"]}
    assert sites["title_generation"]["effective"]["model_id"] == "claude-haiku-4-5-20251001"
    assert sites["title_generation"]["override"] is None
    assert sites["dreaming.the_dreaming"]["pinned"] is True

    # Dreams are pinned.
    r = booted_app.put("/admin/llm-config/dreaming.the_dreaming", headers=_auth(token),
                       json={"provider": "ollama", "model_id": "llama3.1:8b-instruct-q8_0"})
    assert r.status_code == 409
    assert booted_app.put("/admin/llm-config/no.such.site", headers=_auth(token),
                          json={"provider": "ollama", "model_id": "x"}).status_code == 404
    assert booted_app.put("/admin/llm-config/title_generation", headers=_auth(token),
                          json={"provider": "bogus", "model_id": "x"}).status_code == 400

    r = booted_app.put("/admin/llm-config/title_generation", headers=_auth(token),
                       json={"provider": "ollama", "model_id": "llama3.2:3b"})
    assert r.status_code == 200

    fake_llm.queue_text("A Local Title", input_tokens=30, output_tokens=4)
    resp = asyncio.run(llm_caller.call_llm("title_generation", user_prompt="title this"))
    assert resp.provider == "ollama" and resp.model_id == "llama3.2:3b"
    assert fake_llm.calls[-1].source == "ollama"

    body = booted_app.get("/admin/llm-config", params={"days": 1}, headers=_auth(token)).json()
    site = {s["call_site"]: s for s in body["call_sites"]}["title_generation"]
    assert site["override"]["model_id"] == "llama3.2:3b"
    assert site["effective"]["provider"] == "ollama"
    assert site["usage"]["calls"] == 1
    assert site["usage"]["input_tokens"] == 30
    assert site["usage"]["models"] == ["ollama:llama3.2:3b"]

    assert booted_app.delete("/admin/llm-config/title_generation", headers=_auth(token)).status_code == 200
    body = booted_app.get("/admin/llm-config", headers=_auth(token)).json()
    site = {s["call_site"]: s for s in body["call_sites"]}["title_generation"]
    assert site["override"] is None and site["effective"]["provider"] == "anthropic"
