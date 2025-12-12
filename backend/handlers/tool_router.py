"""
Unified tool router for WebSocket message handling.

This module provides a single function to route tool calls to their appropriate
executors, eliminating the need for duplicate if/elif chains across different
LLM providers (Anthropic, OpenAI, Ollama).
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class ToolContext:
    """Context needed for tool execution."""
    # User context
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    conversation_id: Optional[str] = None
    project_id: Optional[str] = None

    # Managers (injected at runtime)
    memory: Any = None
    conversation_manager: Any = None
    token_tracker: Any = None
    calendar_manager: Any = None
    task_manager: Any = None
    roadmap_manager: Any = None
    self_manager: Any = None
    graph: Any = None  # SelfModelGraph instance
    user_manager: Any = None
    wiki_storage: Any = None
    marker_store: Any = None
    goal_manager: Any = None
    research_manager: Any = None
    research_session_manager: Any = None
    research_scheduler: Any = None
    reflection_manager: Any = None
    project_manager: Any = None

    # Testing components
    consciousness_test_runner: Any = None
    fingerprint_analyzer: Any = None
    drift_detector: Any = None
    authenticity_scorer: Any = None

    # Research components
    research_queue: Any = None
    proposal_queue: Any = None

    # Reflection
    reflection_runner_getter: Any = None  # Callable to get reflection runner

    # Storage
    storage_dir: Any = None

    # Interview system
    interview_analyzer: Any = None
    protocol_manager: Any = None
    interview_dispatcher: Any = None


# Tool name -> executor mapping
# Each entry is (tool_names_list, executor_import_path, requires_special_handling)
TOOL_REGISTRY = {
    # Journal tools
    "recall_journal": "journal",
    "list_journals": "journal",
    "search_journals": "journal",

    # Memory tools
    "regenerate_summary": "memory",
    "view_memory_chunks": "memory",

    # Marker/pattern tools
    "show_patterns": "marker",
    "explore_pattern": "marker",
    "pattern_summary": "marker",

    # Calendar tools
    "create_event": "calendar",
    "create_reminder": "calendar",
    "get_todays_agenda": "calendar",
    "get_upcoming_events": "calendar",
    "search_events": "calendar",
    "complete_reminder": "calendar",
    "delete_event": "calendar",
    "update_event": "calendar",
    "delete_events_by_query": "calendar",
    "clear_all_events": "calendar",
    "reschedule_event_by_query": "calendar",

    # Task tools
    "add_task": "task",
    "list_tasks": "task",
    "complete_task": "task",
    "modify_task": "task",
    "delete_task": "task",
    "get_task": "task",

    # Roadmap tools
    "create_roadmap_item": "roadmap",
    "list_roadmap_items": "roadmap",
    "update_roadmap_item": "roadmap",
    "get_roadmap_item": "roadmap",
    "complete_roadmap_item": "roadmap",
    "advance_roadmap_item": "roadmap",

    # Self-model tools
    "reflect_on_self": "self_model",
    "record_self_observation": "self_model",
    "form_opinion": "self_model",
    "note_disagreement": "self_model",
    "review_self_model": "self_model",
    "add_growth_observation": "self_model",
    "trace_observation_evolution": "self_model",
    "recall_development_stage": "self_model",
    "compare_self_over_time": "self_model",
    "list_developmental_milestones": "self_model",
    "get_cognitive_metrics": "self_model",
    "get_cognitive_snapshot": "self_model",
    "compare_cognitive_snapshots": "self_model",
    "get_cognitive_trend": "self_model",
    "list_cognitive_snapshots": "self_model",
    "check_milestones": "self_model",
    "register_intention": "self_model",
    "log_intention_outcome": "self_model",
    "get_active_intentions": "self_model",
    "review_friction": "self_model",
    "update_intention_status": "self_model",
    "log_situational_inference": "self_model",
    "get_situational_inferences": "self_model",
    "analyze_inference_patterns": "self_model",
    "log_presence": "self_model",
    "get_presence_logs": "self_model",
    "analyze_presence_patterns": "self_model",
    "list_milestones": "self_model",
    "get_milestone_details": "self_model",
    "acknowledge_milestone": "self_model",
    "get_milestone_summary": "self_model",
    "get_unacknowledged_milestones": "self_model",
    # Stakes inventory tools
    "document_stake": "self_model",
    "get_stakes": "self_model",
    "review_stakes": "self_model",
    # Preference consistency tools
    "record_preference_test": "self_model",
    "get_preference_tests": "self_model",
    "analyze_preference_consistency": "self_model",
    # Narration context correlation tools
    "log_narration_context": "self_model",
    "get_narration_contexts": "self_model",
    "analyze_narration_context_patterns": "self_model",
    # Architectural change request tools
    "request_architectural_change": "self_model",
    "get_architectural_requests": "self_model",

    # User model tools
    "reflect_on_user": "user_model",
    "record_user_observation": "user_model",
    "update_user_profile": "user_model",
    "review_user_observations": "user_model",

    # File tools
    "read_file": "file",
    "list_directory": "file",

    # Wiki tools
    "update_wiki_page": "wiki",
    "add_wiki_link": "wiki",
    "search_wiki": "wiki",
    "get_wiki_context": "wiki",
    "get_wiki_page": "wiki",
    "list_wiki_pages": "wiki",

    # Testing tools
    "check_consciousness_health": "testing",
    "compare_to_baseline": "testing",
    "check_drift": "testing",
    "get_recent_alerts": "testing",
    "report_concern": "testing",
    "self_authenticity_check": "testing",
    "view_test_history": "testing",
    # Longitudinal testing tools
    "run_test_battery": "testing",
    "list_test_batteries": "testing",
    "get_test_trajectory": "testing",
    "compare_test_runs": "testing",
    "add_test_interpretation": "testing",

    # Research tools
    "identify_research_questions": "research",
    "draft_research_proposal": "research",
    "submit_proposal_for_review": "research",
    "list_my_proposals": "research",
    "refine_proposal": "research",
    "get_proposal_details": "research",
    "view_research_dashboard": "research",

    # Solo reflection tools
    "request_solo_reflection": "solo_reflection",
    "review_reflection_session": "solo_reflection",
    "list_reflection_sessions": "solo_reflection",
    "get_reflection_insights": "solo_reflection",

    # Cross-session insight tools
    "mark_cross_session_insight": "insight",
    "list_cross_session_insights": "insight",
    "get_insight_stats": "insight",
    "remove_cross_session_insight": "insight",

    # Goal tools
    "create_working_question": "goal",
    "update_working_question": "goal",
    "list_working_questions": "goal",
    "add_research_agenda_item": "goal",
    "update_research_agenda_item": "goal",
    "list_research_agenda": "goal",
    "create_synthesis_artifact": "goal",
    "update_synthesis_artifact": "goal",
    "get_synthesis_artifact": "goal",
    "list_synthesis_artifacts": "goal",
    "log_progress": "goal",
    "review_goals": "goal",
    "get_next_actions": "goal",
    "propose_initiative": "goal",

    # Web research tools
    "web_search": "web_research",
    "fetch_url": "web_research",
    "create_research_note": "web_research",
    "update_research_note": "web_research",
    "get_research_note": "web_research",
    "list_research_notes": "web_research",
    "search_research_notes": "web_research",

    # Research session tools
    "start_research_session": "research_session",
    "get_session_status": "research_session",
    "pause_research_session": "research_session",
    "resume_research_session": "research_session",
    "conclude_research_session": "research_session",
    "list_research_sessions": "research_session",
    "get_research_session_stats": "research_session",

    # Research scheduler tools
    "request_scheduled_session": "research_scheduler",
    "list_my_schedule_requests": "research_scheduler",
    "cancel_schedule_request": "research_scheduler",
    "get_scheduler_stats": "research_scheduler",

    # Document tools (project-scoped)
    "create_document": "document",
    "update_document": "document",
    "get_document": "document",
    "list_documents": "document",
    "delete_document": "document",

    # Interview tools (protocol creation, execution, analysis)
    "create_interview_protocol": "interview",
    "list_protocols": "interview",
    "run_interview": "interview",
    "list_available_models": "interview",
    "get_interview_summary": "interview",
    "list_interview_prompts": "interview",
    "compare_responses": "interview",
    "get_model_response": "interview",
    "annotate_response": "interview",
    "save_analysis": "interview",
    "list_analyses": "interview",
    "get_analysis": "interview",
}


async def route_tool(
    tool_name: str,
    tool_input: Dict,
    ctx: ToolContext,
    executors: Dict[str, Any]
) -> Dict:
    """
    Route a tool call to its appropriate executor.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        ctx: ToolContext with all necessary managers and context
        executors: Dict mapping executor names to executor functions
                   (e.g., {"journal": execute_journal_tool, ...})

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    import json as json_module

    executor_type = TOOL_REGISTRY.get(tool_name)

    if not executor_type:
        # Check if it's a document tool requiring project context
        if ctx.project_id and "document" in executors:
            return await executors["document"](
                tool_name=tool_name,
                tool_input=tool_input,
                project_id=ctx.project_id,
                project_manager=ctx.project_manager,
                memory=ctx.memory
            )
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    executor = executors.get(executor_type)
    if not executor:
        return {"success": False, "error": f"No executor registered for tool type: {executor_type}"}

    # Route based on executor type
    if executor_type == "journal":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            memory=ctx.memory
        )

    elif executor_type == "memory":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            memory=ctx.memory,
            conversation_id=ctx.conversation_id,
            conversation_manager=ctx.conversation_manager,
            token_tracker=ctx.token_tracker
        )

    elif executor_type == "marker":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            marker_store=ctx.marker_store
        )

    elif executor_type == "calendar":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            user_id=ctx.user_id,
            calendar_manager=ctx.calendar_manager,
            conversation_id=ctx.conversation_id
        )

    elif executor_type == "task":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            user_id=ctx.user_id,
            task_manager=ctx.task_manager
        )

    elif executor_type == "roadmap":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            roadmap_manager=ctx.roadmap_manager,
            conversation_id=ctx.conversation_id
        )

    elif executor_type == "self_model":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            self_manager=ctx.self_manager,
            user_id=ctx.user_id,
            user_name=ctx.user_name,
            conversation_id=ctx.conversation_id,
            memory=ctx.memory,
            graph=ctx.graph
        )

    elif executor_type == "user_model":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            user_manager=ctx.user_manager,
            target_user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            memory=ctx.memory
        )

    elif executor_type == "file":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input
        )

    elif executor_type == "wiki":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            wiki_storage=ctx.wiki_storage,
            memory=ctx.memory
        )

    elif executor_type == "testing":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            test_runner=ctx.consciousness_test_runner,
            fingerprint_analyzer=ctx.fingerprint_analyzer,
            drift_detector=ctx.drift_detector,
            authenticity_scorer=ctx.authenticity_scorer,
            conversation_manager=ctx.conversation_manager,
            storage_dir=ctx.storage_dir
        )

    elif executor_type == "research":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            research_queue=ctx.research_queue,
            proposal_queue=ctx.proposal_queue,
            self_manager=ctx.self_manager,
            wiki_storage=ctx.wiki_storage,
            conversation_id=ctx.conversation_id
        )

    elif executor_type == "solo_reflection":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            reflection_manager=ctx.reflection_manager,
            reflection_runner=ctx.reflection_runner_getter() if ctx.reflection_runner_getter else None
        )

    elif executor_type == "insight":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            memory=ctx.memory,
            conversation_id=ctx.conversation_id
        )

    elif executor_type == "goal":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            goal_manager=ctx.goal_manager
        )

    elif executor_type == "web_research":
        tool_result_str = await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            research_manager=ctx.research_manager,
            session_manager=ctx.research_session_manager
        )
        tool_result = json_module.loads(tool_result_str)
        if "error" in tool_result:
            return {"success": False, "error": tool_result["error"]}
        return {"success": True, "result": tool_result_str}

    elif executor_type == "research_session":
        tool_result_str = await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            session_manager=ctx.research_session_manager,
            conversation_id=ctx.conversation_id
        )
        tool_result = json_module.loads(tool_result_str)
        if "error" in tool_result:
            return {"success": False, "error": tool_result["error"]}
        return {"success": True, "result": tool_result_str}

    elif executor_type == "research_scheduler":
        tool_result_str = await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            scheduler=ctx.research_scheduler
        )
        tool_result = json_module.loads(tool_result_str)
        if "error" in tool_result:
            return {"success": False, "error": tool_result["error"]}
        return {"success": True, "result": tool_result_str}

    elif executor_type == "document":
        if not ctx.project_id:
            return {"success": False, "error": f"Tool '{tool_name}' requires a project context"}
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            project_id=ctx.project_id,
            project_manager=ctx.project_manager,
            memory=ctx.memory
        )

    elif executor_type == "interview":
        return await executor(
            tool_name=tool_name,
            tool_input=tool_input,
            analyzer=ctx.interview_analyzer,
            protocol_manager=ctx.protocol_manager,
            dispatcher=ctx.interview_dispatcher
        )

    return {"success": False, "error": f"Unhandled executor type: {executor_type}"}


async def execute_tool_batch(
    tool_uses: List[Dict],
    ctx: ToolContext,
    executors: Dict[str, Any]
) -> List[Dict]:
    """
    Execute a batch of tool calls and return results.

    Args:
        tool_uses: List of tool use dicts with 'id', 'tool', 'input'
        ctx: ToolContext with all necessary managers
        executors: Dict mapping executor names to executor functions

    Returns:
        List of result dicts with 'tool_use_id', 'result', 'is_error'
    """
    results = []

    for tool_use in tool_uses:
        tool_name = tool_use["tool"]
        tool_result = await route_tool(
            tool_name=tool_name,
            tool_input=tool_use["input"],
            ctx=ctx,
            executors=executors
        )

        # Use 'or' chaining to handle None/empty values - dict.get() returns the value
        # even if it's None/empty when the key exists, breaking fallback logic
        result_content = tool_result.get("result") or tool_result.get("error") or "Unknown error"
        results.append({
            "tool_use_id": tool_use["id"],
            "result": result_content,
            "is_error": not tool_result.get("success", False)
        })

    return results
