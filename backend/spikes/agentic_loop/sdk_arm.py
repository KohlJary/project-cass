"""
Arm A: the Claude Agent SDK (Claude Code as the harness).

Same system prompt, task, workspace and tools as the own loop. Her tools and
the spike's tools are an in-process MCP server ("cass"). Claude Code's own file
tools (Read, Write, Edit, Glob, Grep) stand in for the own loop's file tools;
shell, web, subagents and notebooks are off. A PreToolUse hook fences every
path to the workspace.

Isolation from Kohl's Claude Code: setting_sources=[] (no settings, hooks or
CLAUDE.md files) and CLAUDE_CONFIG_DIR pointed at a scratch folder.

With base_url set, the CLI talks to an Anthropic-compatible proxy (LiteLLM)
instead of Anthropic, so a non-Claude model runs in the same harness.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .common import TASK, RunRecord, system_prompt, tool_set

DISALLOWED = ["Bash", "BashOutput", "KillShell", "KillBash", "WebFetch", "WebSearch", "Task",
              "NotebookEdit", "SlashCommand", "Skill", "ExitPlanMode"]
PATH_KEYS = ("file_path", "path", "notebook_path")


def _fence_hook(ws: Path):
    async def hook(input_data: Dict[str, Any], tool_use_id: Optional[str], context: Any) -> Dict[str, Any]:
        tool_input = input_data.get("tool_input") or {}
        for key in PATH_KEYS:
            val = tool_input.get(key)
            if val:
                p = (ws / val).resolve() if not os.path.isabs(val) else Path(val).resolve()
                if not (p == ws or ws in p.parents):
                    return {"hookSpecificOutput": {
                        "hookEventName": "PreToolUse", "permissionDecision": "deny",
                        "permissionDecisionReason": "That path is outside your workspace."}}
        return {}
    return hook


async def _run(ws: Path, model: str, base_url: Optional[str], max_turns: int, budget_usd: float) -> RunRecord:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher,
                                  ResultMessage, TextBlock, ToolUseBlock, create_sdk_mcp_server, tool)

    rec = RunRecord(arm="sdk/" + ("proxy" if base_url else "anthropic"), model=model)
    specs = tool_set()

    def make(spec):
        @tool(spec["name"], spec["description"][:1000], spec["input_schema"])
        async def handler(args):
            return {"content": [{"type": "text", "text": rec.spike_tool(spec["name"], args)}]}
        return handler

    server = create_sdk_mcp_server("cass", tools=[make(s) for s in specs])

    config_dir = Path(tempfile.mkdtemp(prefix="agentic_spike_claude_cfg_"))
    env = {"CLAUDE_CONFIG_DIR": str(config_dir), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
           "DISABLE_AUTOUPDATER": "1"}
    if base_url:
        env.update({"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_API_KEY": os.environ.get("SPIKE_PROXY_KEY", "sk-spike-proxy"),
                    "ANTHROPIC_SMALL_FAST_MODEL": model, "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
                    "ANTHROPIC_DEFAULT_SONNET_MODEL": model, "ANTHROPIC_DEFAULT_OPUS_MODEL": model})
    else:
        env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]

    options = ClaudeAgentOptions(
        system_prompt=system_prompt(ws),
        model=model,
        cwd=str(ws),
        setting_sources=[],
        mcp_servers={"cass": server},
        disallowed_tools=DISALLOWED,
        permission_mode="bypassPermissions",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_fence_hook(ws)])]},
        max_turns=max_turns,
        max_budget_usd=budget_usd,
        env=env,
    )
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(TASK)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    rec.steps += 1
                    entry: Dict[str, Any] = {"step": rec.steps, "text": "", "calls": []}
                    for b in msg.content:
                        if isinstance(b, TextBlock):
                            entry["text"] += b.text
                        elif isinstance(b, ToolUseBlock):
                            entry["calls"].append({"name": b.name, "input": b.input})
                            if not b.name.startswith("mcp__cass__"):
                                rec.tool_calls.append({"name": b.name, "input": b.input})
                    rec.transcript.append(entry)
                elif isinstance(msg, ResultMessage):
                    usage = msg.usage or {}
                    rec.input_tokens = (usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                                        + usage.get("cache_creation_input_tokens", 0))
                    rec.output_tokens = usage.get("output_tokens", 0)
                    rec.cost_usd = msg.total_cost_usd if not base_url else None
                    rec.ended_how = "done" if rec.done_summary is not None else (msg.subtype or "ended")
                    if msg.is_error:
                        rec.error = f"{msg.subtype}: {msg.result}"
    except Exception as e:
        rec.ended_how, rec.error = "error", f"{type(e).__name__}: {e}"
    if rec.done_summary is not None:
        rec.ended_how = "done"
    rec.ended = time.time()
    # Her and the spike's MCP tools are recorded by their handlers; strip the prefix in counts.
    for c in rec.tool_calls:
        c["name"] = c["name"].removeprefix("mcp__cass__")
    return rec


def run(ws: Path, model: str, base_url: Optional[str] = None, max_turns: int = 60, budget_usd: float = 3.0) -> RunRecord:
    return asyncio.run(_run(ws.resolve(), model, base_url, max_turns, budget_usd))
