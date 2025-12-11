#!/usr/bin/env python3
"""
Backend Capability Scanner

Scans the cass-vessel backend to build a comprehensive capability index.
Combines git history analysis with code inspection to produce an up-to-date
inventory of everything the system can do.

Usage:
    python scripts/capability_scanner.py [--output FILE] [--format json|markdown]

Output:
    - JSON capability index (default: data/capability_index.json)
    - Optionally markdown report for human review
"""

import argparse
import ast
import json
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set


@dataclass
class Endpoint:
    """An API endpoint."""
    path: str
    method: str
    handler: str
    file: str
    line: int
    description: Optional[str] = None


@dataclass
class Tool:
    """A tool available to Cass."""
    name: str
    category: str  # from tool_router.py registry
    description: Optional[str] = None
    file: str = ""
    parameters: List[str] = field(default_factory=list)


@dataclass
class DataModel:
    """A data model/storage class."""
    name: str
    file: str
    fields: List[str] = field(default_factory=list)
    description: Optional[str] = None


@dataclass
class ScheduledTask:
    """A background/scheduled task."""
    name: str
    schedule: str
    file: str
    description: Optional[str] = None


@dataclass
class Capability:
    """A logical capability grouping."""
    id: str
    name: str
    category: str  # api, tools, data, scheduler, config
    description: str
    endpoints: List[Endpoint] = field(default_factory=list)
    tools: List[Tool] = field(default_factory=list)
    data_models: List[DataModel] = field(default_factory=list)
    scheduled_tasks: List[ScheduledTask] = field(default_factory=list)
    admin_ui_path: Optional[str] = None
    status: str = "complete"  # complete, partial, deprecated
    commits: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class CapabilityIndex:
    """Complete capability index."""
    generated_at: str
    git_commit: str
    capabilities: List[Capability] = field(default_factory=list)
    uncategorized_endpoints: List[Endpoint] = field(default_factory=list)
    uncategorized_tools: List[Tool] = field(default_factory=list)
    scan_notes: List[str] = field(default_factory=list)


class CapabilityScanner:
    """Scans backend code to build capability index."""

    def __init__(self, backend_dir: Path):
        self.backend_dir = backend_dir
        self.repo_root = backend_dir.parent

    def get_git_commit(self) -> str:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            return result.stdout.strip()[:12]
        except Exception:
            return "unknown"

    def scan_endpoints(self) -> List[Endpoint]:
        """Scan FastAPI route definitions."""
        endpoints = []

        # Patterns to match FastAPI decorators
        route_pattern = re.compile(
            r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
            re.IGNORECASE
        )

        # Scan main_sdk.py and routes/
        files_to_scan = [self.backend_dir / "main_sdk.py"]
        routes_dir = self.backend_dir / "routes"
        if routes_dir.exists():
            files_to_scan.extend(routes_dir.glob("*.py"))

        for file_path in files_to_scan:
            if not file_path.exists():
                continue

            content = file_path.read_text()
            lines = content.split('\n')

            for i, line in enumerate(lines):
                match = route_pattern.search(line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)

                    # Try to get function name from next non-decorator line
                    handler = "unknown"
                    for j in range(i + 1, min(i + 5, len(lines))):
                        func_match = re.match(r'\s*(?:async\s+)?def\s+(\w+)', lines[j])
                        if func_match:
                            handler = func_match.group(1)
                            break

                    # Try to extract docstring
                    description = None
                    for j in range(i + 1, min(i + 10, len(lines))):
                        doc_match = re.search(r'"""(.+?)"""', lines[j])
                        if doc_match:
                            description = doc_match.group(1).strip()
                            break

                    endpoints.append(Endpoint(
                        path=path,
                        method=method,
                        handler=handler,
                        file=str(file_path.relative_to(self.backend_dir)),
                        line=i + 1,
                        description=description
                    ))

        return endpoints

    def scan_tools(self) -> List[Tool]:
        """Scan tool definitions from tool_router.py and handler files."""
        tools = []

        # First, get the registry mapping from tool_router.py
        router_path = self.backend_dir / "handlers" / "tool_router.py"
        if not router_path.exists():
            return tools

        content = router_path.read_text()

        # Extract TOOL_REGISTRY entries
        registry_pattern = re.compile(r'"(\w+)":\s*"(\w+)"')
        tool_categories = {}

        in_registry = False
        for line in content.split('\n'):
            if 'TOOL_REGISTRY' in line and '=' in line:
                in_registry = True
            elif in_registry:
                if line.strip() == '}':
                    in_registry = False
                else:
                    match = registry_pattern.search(line)
                    if match:
                        tool_name, category = match.groups()
                        tool_categories[tool_name] = category

        # Now scan handler files for tool definitions with descriptions
        handlers_dir = self.backend_dir / "handlers"
        if handlers_dir.exists():
            for handler_file in handlers_dir.glob("*.py"):
                content = handler_file.read_text()

                # Look for tool definition dicts
                # Pattern: {"name": "tool_name", "description": "..."}
                tool_def_pattern = re.compile(
                    r'\{\s*"name":\s*"(\w+)"[^}]*"description":\s*"([^"]+)"',
                    re.DOTALL
                )

                for match in tool_def_pattern.finditer(content):
                    name = match.group(1)
                    description = match.group(2)
                    category = tool_categories.get(name, "unknown")

                    tools.append(Tool(
                        name=name,
                        category=category,
                        description=description[:200] + "..." if len(description) > 200 else description,
                        file=str(handler_file.relative_to(self.backend_dir))
                    ))

        # Add any tools from registry not found in handlers
        found_tools = {t.name for t in tools}
        for tool_name, category in tool_categories.items():
            if tool_name not in found_tools:
                tools.append(Tool(
                    name=tool_name,
                    category=category,
                    file="handlers/tool_router.py"
                ))

        return tools

    def scan_data_models(self) -> List[DataModel]:
        """Scan for data model classes (dataclasses, Pydantic models)."""
        models = []

        # Files likely to contain models
        files_to_scan = list(self.backend_dir.glob("*.py"))
        files_to_scan.extend(self.backend_dir.glob("**/*.py"))

        dataclass_pattern = re.compile(r'@dataclass\s*\n\s*class\s+(\w+)')
        pydantic_pattern = re.compile(r'class\s+(\w+)\s*\(\s*(?:Base)?Model\s*\)')

        seen = set()

        for file_path in files_to_scan:
            if '__pycache__' in str(file_path) or 'venv' in str(file_path):
                continue

            try:
                content = file_path.read_text()
            except Exception:
                continue

            for pattern in [dataclass_pattern, pydantic_pattern]:
                for match in pattern.finditer(content):
                    name = match.group(1)
                    if name not in seen:
                        seen.add(name)
                        models.append(DataModel(
                            name=name,
                            file=str(file_path.relative_to(self.backend_dir))
                        ))

        return models

    def scan_scheduled_tasks(self) -> List[ScheduledTask]:
        """Scan for APScheduler or similar scheduled tasks."""
        tasks = []

        # Look for scheduler patterns
        scheduler_patterns = [
            re.compile(r'scheduler\.add_job\s*\(\s*(\w+)'),
            re.compile(r'@scheduler\.scheduled_job\s*\([^)]*\)\s*\n\s*(?:async\s+)?def\s+(\w+)'),
            re.compile(r'cron\s*\([^)]*\)\s*\n\s*(?:async\s+)?def\s+(\w+)'),
        ]

        for file_path in self.backend_dir.glob("**/*.py"):
            if '__pycache__' in str(file_path):
                continue

            try:
                content = file_path.read_text()
            except Exception:
                continue

            for pattern in scheduler_patterns:
                for match in pattern.finditer(content):
                    task_name = match.group(1)
                    tasks.append(ScheduledTask(
                        name=task_name,
                        schedule="see code",
                        file=str(file_path.relative_to(self.backend_dir))
                    ))

        return tasks

    def analyze_git_history(self) -> Dict[str, List[str]]:
        """Extract feature context from git commit messages."""
        features = {}

        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--no-merges", "-100"],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                # Extract keywords that might indicate capabilities
                keywords = ['add', 'implement', 'feature', 'tool', 'endpoint', 'api']
                line_lower = line.lower()

                for keyword in keywords:
                    if keyword in line_lower:
                        # Try to extract the feature name
                        commit_hash = line.split()[0]
                        message = ' '.join(line.split()[1:])

                        if message not in features:
                            features[message] = []
                        features[message].append(commit_hash)
                        break

        except Exception as e:
            pass

        return features

    def categorize_capabilities(
        self,
        endpoints: List[Endpoint],
        tools: List[Tool],
        models: List[DataModel],
        tasks: List[ScheduledTask]
    ) -> List[Capability]:
        """Group discovered items into logical capabilities."""

        # Define capability mappings based on path/name patterns
        capability_patterns = {
            "calendar": {
                "name": "Calendar & Events",
                "category": "tools",
                "description": "Event and reminder management",
                "path_patterns": [r"/calendar", r"/events", r"/reminders", r"/today", r"/upcoming"],
                "tool_patterns": [r"^create_event$", r"^create_reminder$", r"^get_todays_agenda$",
                                  r"^get_upcoming_events$", r"^search_events$", r"^complete_reminder$",
                                  r"^delete_event$", r"^update_event$", r"^delete_events_by_query$",
                                  r"^clear_all_events$", r"^reschedule_event_by_query$"],
                "file_patterns": [r"calendar"],
            },
            "tasks": {
                "name": "Task Management",
                "category": "tools",
                "description": "Task tracking with Taskwarrior integration",
                "path_patterns": [r"/tasks"],
                "tool_patterns": [r"^add_task$", r"^list_tasks$", r"^complete_task$",
                                  r"^modify_task$", r"^delete_task$", r"^get_task$"],
                "file_patterns": [r"tasks\.py"],
            },
            "memory": {
                "name": "Memory System",
                "category": "data",
                "description": "Conversation storage, summarization, and retrieval",
                "path_patterns": [r"/memory", r"/summar"],
                "tool_patterns": [r"summary", r"memory", r"chunk", r"regenerate_summary", r"view_memory"],
                "file_patterns": [r"memory"],
            },
            "journal": {
                "name": "Journaling",
                "category": "tools",
                "description": "Daily reflection and journal entries",
                "path_patterns": [r"/journal"],
                "tool_patterns": [r"journal"],
                "file_patterns": [r"journal"],
            },
            "wiki": {
                "name": "Wiki System",
                "category": "tools",
                "description": "Knowledge base and documentation",
                "path_patterns": [r"/wiki", r"/pages", r"/graph", r"/search", r"/bootstrap", r"/retrieve", r"/analyze-conversation", r"/populate"],
                "tool_patterns": [r"wiki"],
                "file_patterns": [r"wiki"],
            },
            "self_model": {
                "name": "Self-Model",
                "category": "tools",
                "description": "Cass's self-understanding, growth edges, observations",
                "path_patterns": [r"/cass", r"/self"],
                "tool_patterns": [r"^reflect_on_self$", r"^record_self_observation$", r"^form_opinion$",
                                  r"^note_disagreement$", r"^review_self_model$", r"^add_growth_observation$",
                                  r"^trace_observation_evolution$", r"^recall_development_stage$",
                                  r"^compare_self_over_time$", r"^list_developmental_milestones$",
                                  r"^get_cognitive", r"^compare_cognitive", r"^list_cognitive",
                                  r"^check_milestones$", r"^list_milestones$", r"^get_milestone",
                                  r"^acknowledge_milestone$", r"^get_unacknowledged"],
                "file_patterns": [r"self_model", r"self_manager"],
            },
            "user_model": {
                "name": "User Modeling",
                "category": "tools",
                "description": "User profiles and observations",
                "path_patterns": [r"/user"],
                "tool_patterns": [r"^reflect_on_user$", r"^record_user_observation$",
                                  r"^update_user_profile$", r"^review_user_observations$"],
                "file_patterns": [r"user"],
            },
            "projects": {
                "name": "Project Management",
                "category": "api",
                "description": "Project workspaces and documents",
                "path_patterns": [r"/project"],
                "tool_patterns": [r"document"],
                "file_patterns": [r"project"],
            },
            "roadmap": {
                "name": "Roadmap",
                "category": "tools",
                "description": "Development planning and tracking",
                "path_patterns": [r"/roadmap"],
                "tool_patterns": [r"roadmap"],
                "file_patterns": [r"roadmap"],
            },
            "research": {
                "name": "Research System",
                "category": "tools",
                "description": "Research proposals, sessions, and web research",
                "path_patterns": [r"/research"],
                "tool_patterns": [r"research", r"^web_search$", r"^fetch_url$", r"proposal",
                                  r"session", r"scheduler"],
                "file_patterns": [r"research"],
            },
            "interviews": {
                "name": "Model Interviews",
                "category": "tools",
                "description": "Interview protocols for studying AI model behavior",
                "path_patterns": [r"/interview"],
                "tool_patterns": [r"interview", r"protocol", r"compare_response", r"annotate_response"],
                "file_patterns": [r"interview"],
            },
            "reflection": {
                "name": "Solo Reflection",
                "category": "tools",
                "description": "Private contemplation sessions",
                "path_patterns": [r"/solo-reflection", r"/reflection"],
                "tool_patterns": [r"reflection", r"solo"],
                "file_patterns": [r"reflection"],
            },
            "testing": {
                "name": "Consciousness Testing",
                "category": "tools",
                "description": "Authenticity scoring, drift detection, fingerprinting",
                "path_patterns": [r"/test", r"/fingerprint", r"/drift", r"/authenticity", r"/probe",
                                  r"/experiment", r"/snapshot", r"/rollback", r"/deploy"],
                "tool_patterns": [r"consciousness", r"drift", r"authenticity", r"fingerprint",
                                  r"baseline", r"check_drift", r"report_concern"],
                "file_patterns": [r"testing"],
            },
            "conversations": {
                "name": "Conversations",
                "category": "api",
                "description": "Conversation management and history",
                "path_patterns": [r"/conversation"],
                "tool_patterns": [],
                "file_patterns": [r"conversation"],
            },
            "tts": {
                "name": "Text-to-Speech",
                "category": "api",
                "description": "Voice synthesis with Piper",
                "path_patterns": [r"/tts", r"/audio"],
                "tool_patterns": [],
                "file_patterns": [r"tts"],
            },
            "goals": {
                "name": "Goals & Synthesis",
                "category": "tools",
                "description": "Working questions, research agenda, synthesis artifacts",
                "path_patterns": [r"/goal", r"/questions", r"/agenda", r"/artifacts", r"/initiatives",
                                  r"/progress", r"/review", r"/next-actions"],
                "tool_patterns": [r"goal", r"synthesis", r"working_question", r"^add_research_agenda",
                                  r"^update_research_agenda", r"^list_research_agenda", r"^log_progress$",
                                  r"^review_goals$", r"^get_next_actions$", r"^propose_initiative$"],
                "file_patterns": [r"goals\.py"],
            },
            "settings": {
                "name": "Settings & Configuration",
                "category": "api",
                "description": "LLM provider, model selection, preferences",
                "path_patterns": [r"/settings", r"/llm-provider", r"/llm-model", r"/ollama", r"/preferences", r"/themes"],
                "tool_patterns": [],
                "file_patterns": [],
            },
            "auth": {
                "name": "Authentication",
                "category": "api",
                "description": "User registration, login, sessions",
                "path_patterns": [r"/register", r"/login", r"/refresh", r"/me"],
                "tool_patterns": [],
                "file_patterns": [r"auth"],
            },
            "files": {
                "name": "File Operations",
                "category": "api",
                "description": "File system operations for projects",
                "path_patterns": [r"/create", r"/mkdir", r"/rename", r"/delete", r"/read", r"/list", r"/exists"],
                "tool_patterns": [],
                "file_patterns": [r"files\.py"],
            },
            "terminal": {
                "name": "Terminal Sessions",
                "category": "api",
                "description": "Terminal/PTY session management for Daedalus",
                "path_patterns": [r"/debug", r"/sessions", r"/capture", r"/send"],
                "tool_patterns": [],
                "file_patterns": [r"terminal"],
            },
            "markers": {
                "name": "Pattern Markers",
                "category": "tools",
                "description": "Conversation pattern detection and analysis",
                "path_patterns": [r"/marker", r"/pattern"],
                "tool_patterns": [r"pattern", r"marker", r"^show_patterns$", r"^explore_pattern$"],
                "file_patterns": [r"marker"],
            },
            "insights": {
                "name": "Cross-Session Insights",
                "category": "tools",
                "description": "Persistent insights across conversations",
                "path_patterns": [r"/insight"],
                "tool_patterns": [r"insight", r"cross_session"],
                "file_patterns": [r"insight"],
            },
            "core": {
                "name": "Core System",
                "category": "api",
                "description": "Health checks, status, chat endpoint",
                "path_patterns": [r"^/$", r"/health", r"/status", r"/chat", r"/gestures"],
                "tool_patterns": [],
                "file_patterns": [],
            },
            "git": {
                "name": "Git Operations",
                "category": "api",
                "description": "Git repository operations",
                "path_patterns": [r"/git"],
                "tool_patterns": [],
                "file_patterns": [r"git\.py"],
            },
            "export": {
                "name": "Data Export",
                "category": "api",
                "description": "Export conversations, memories, data",
                "path_patterns": [r"/export"],
                "tool_patterns": [],
                "file_patterns": [r"export"],
            },
            "github": {
                "name": "GitHub Integration",
                "category": "api",
                "description": "GitHub metrics and integration",
                "path_patterns": [r"/github"],
                "tool_patterns": [],
                "file_patterns": [r"github"],
            },
        }

        capabilities = {}
        used_endpoints = set()
        used_tools = set()

        for cap_id, cap_def in capability_patterns.items():
            cap = Capability(
                id=cap_id,
                name=cap_def["name"],
                category=cap_def["category"],
                description=cap_def["description"]
            )

            file_patterns = cap_def.get("file_patterns", [])

            # Match endpoints by path OR file
            for endpoint in endpoints:
                if id(endpoint) in used_endpoints:
                    continue
                matched = False
                # Try path patterns
                for pattern in cap_def["path_patterns"]:
                    if re.search(pattern, endpoint.path, re.IGNORECASE):
                        matched = True
                        break
                # Try file patterns if not matched
                if not matched and file_patterns:
                    for pattern in file_patterns:
                        if re.search(pattern, endpoint.file, re.IGNORECASE):
                            matched = True
                            break
                if matched:
                    cap.endpoints.append(endpoint)
                    used_endpoints.add(id(endpoint))

            # Match tools by name OR file
            for tool in tools:
                if id(tool) in used_tools:
                    continue
                matched = False
                # Try tool name patterns
                for pattern in cap_def["tool_patterns"]:
                    if re.search(pattern, tool.name, re.IGNORECASE):
                        matched = True
                        break
                # Try file patterns if not matched
                if not matched and file_patterns:
                    for pattern in file_patterns:
                        if re.search(pattern, tool.file, re.IGNORECASE):
                            matched = True
                            break
                if matched:
                    cap.tools.append(tool)
                    used_tools.add(id(tool))

            if cap.endpoints or cap.tools:
                capabilities[cap_id] = cap

        # Collect uncategorized items
        uncategorized_endpoints = [e for e in endpoints if id(e) not in used_endpoints]
        uncategorized_tools = [t for t in tools if id(t) not in used_tools]

        return list(capabilities.values()), uncategorized_endpoints, uncategorized_tools

    def scan(self) -> CapabilityIndex:
        """Run full capability scan."""
        print("Scanning endpoints...")
        endpoints = self.scan_endpoints()
        print(f"  Found {len(endpoints)} endpoints")

        print("Scanning tools...")
        tools = self.scan_tools()
        print(f"  Found {len(tools)} tools")

        print("Scanning data models...")
        models = self.scan_data_models()
        print(f"  Found {len(models)} data models")

        print("Scanning scheduled tasks...")
        tasks = self.scan_scheduled_tasks()
        print(f"  Found {len(tasks)} scheduled tasks")

        print("Analyzing git history...")
        git_features = self.analyze_git_history()
        print(f"  Found {len(git_features)} feature-related commits")

        print("Categorizing capabilities...")
        capabilities, uncategorized_endpoints, uncategorized_tools = self.categorize_capabilities(
            endpoints, tools, models, tasks
        )
        print(f"  Organized into {len(capabilities)} capability groups")

        # Add data models and tasks to relevant capabilities
        # (simplified - just attach to first matching capability)
        for model in models:
            for cap in capabilities:
                if cap.id.lower() in model.file.lower() or cap.id.lower() in model.name.lower():
                    cap.data_models.append(model)
                    break

        for task in tasks:
            for cap in capabilities:
                if cap.id.lower() in task.file.lower() or cap.id.lower() in task.name.lower():
                    cap.scheduled_tasks.append(task)
                    break

        return CapabilityIndex(
            generated_at=datetime.now().isoformat(),
            git_commit=self.get_git_commit(),
            capabilities=capabilities,
            uncategorized_endpoints=uncategorized_endpoints,
            uncategorized_tools=uncategorized_tools,
            scan_notes=[
                f"Scanned {len(endpoints)} total endpoints",
                f"Scanned {len(tools)} total tools",
                f"Found {len(uncategorized_endpoints)} uncategorized endpoints",
                f"Found {len(uncategorized_tools)} uncategorized tools",
            ]
        )


def to_dict_recursive(obj):
    """Convert dataclass instances to dicts recursively."""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: to_dict_recursive(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, list):
        return [to_dict_recursive(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: to_dict_recursive(v) for k, v in obj.items()}
    return obj


def generate_markdown_report(index: CapabilityIndex) -> str:
    """Generate human-readable markdown report."""
    lines = [
        "# Backend Capability Index",
        "",
        f"Generated: {index.generated_at}",
        f"Git Commit: {index.git_commit}",
        "",
        "## Summary",
        "",
        f"- **{len(index.capabilities)}** capability groups",
        f"- **{sum(len(c.endpoints) for c in index.capabilities)}** categorized endpoints",
        f"- **{sum(len(c.tools) for c in index.capabilities)}** categorized tools",
        f"- **{len(index.uncategorized_endpoints)}** uncategorized endpoints",
        f"- **{len(index.uncategorized_tools)}** uncategorized tools",
        "",
        "---",
        "",
    ]

    # Capability details
    for cap in sorted(index.capabilities, key=lambda c: c.name):
        lines.append(f"## {cap.name}")
        lines.append("")
        lines.append(f"**Category:** {cap.category}")
        lines.append(f"**Description:** {cap.description}")
        lines.append("")

        if cap.endpoints:
            lines.append("### Endpoints")
            lines.append("")
            for ep in cap.endpoints:
                lines.append(f"- `{ep.method} {ep.path}` - {ep.handler} ({ep.file}:{ep.line})")
            lines.append("")

        if cap.tools:
            lines.append("### Tools")
            lines.append("")
            for tool in cap.tools:
                desc = f" - {tool.description}" if tool.description else ""
                lines.append(f"- `{tool.name}`{desc}")
            lines.append("")

        if cap.data_models:
            lines.append("### Data Models")
            lines.append("")
            for model in cap.data_models:
                lines.append(f"- `{model.name}` ({model.file})")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Uncategorized items
    if index.uncategorized_endpoints:
        lines.append("## Uncategorized Endpoints")
        lines.append("")
        lines.append("*These endpoints need to be assigned to a capability group:*")
        lines.append("")
        for ep in index.uncategorized_endpoints:
            lines.append(f"- `{ep.method} {ep.path}` ({ep.file}:{ep.line})")
        lines.append("")

    if index.uncategorized_tools:
        lines.append("## Uncategorized Tools")
        lines.append("")
        lines.append("*These tools need to be assigned to a capability group:*")
        lines.append("")
        for tool in index.uncategorized_tools:
            lines.append(f"- `{tool.name}` (category: {tool.category})")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Scan backend capabilities")
    parser.add_argument(
        "--output", "-o",
        default="data/capability_index.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--markdown", "-m",
        help="Also generate markdown report to this path"
    )
    parser.add_argument(
        "--backend-dir",
        default=None,
        help="Backend directory (default: auto-detect)"
    )

    args = parser.parse_args()

    # Find backend directory
    if args.backend_dir:
        backend_dir = Path(args.backend_dir)
    else:
        # Try to find it relative to script location
        script_dir = Path(__file__).parent
        backend_dir = script_dir.parent / "backend"
        if not backend_dir.exists():
            backend_dir = script_dir / "backend"

    if not backend_dir.exists():
        print(f"Error: Backend directory not found at {backend_dir}")
        return 1

    print(f"Scanning backend at: {backend_dir}")
    print("")

    scanner = CapabilityScanner(backend_dir)
    index = scanner.scan()

    # Write JSON output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(to_dict_recursive(index), f, indent=2)

    print(f"\nJSON index written to: {output_path}")

    # Write markdown if requested
    if args.markdown:
        markdown_path = Path(args.markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)

        report = generate_markdown_report(index)
        with open(markdown_path, 'w') as f:
            f.write(report)

        print(f"Markdown report written to: {markdown_path}")

    # Print summary
    print("\n" + "=" * 50)
    print("SCAN COMPLETE")
    print("=" * 50)
    for note in index.scan_notes:
        print(f"  {note}")

    return 0


if __name__ == "__main__":
    exit(main())
