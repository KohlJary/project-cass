"""
Goal Generation and Tracking System

Enables Cass to set her own objectives, track progress toward them,
and synthesize positions that persist and evolve across sessions.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class GoalManager:
    """
    Manages Cass's goal system: working questions, research agenda,
    synthesis artifacts, and progress tracking.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "goals"
        self._daemon_id = None  # Lazy-loaded for event emission

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.synthesis_dir = self.data_dir / "synthesis"
        self.synthesis_dir.mkdir(exist_ok=True)

        self.questions_file = self.data_dir / "working_questions.json"
        self.agenda_file = self.data_dir / "research_agenda.json"
        self.progress_file = self.data_dir / "progress_log.json"
        self.initiatives_file = self.data_dir / "initiatives.json"

        # Initialize files if they don't exist
        self._ensure_files()

    def _get_daemon_id(self) -> Optional[str]:
        """Get daemon ID for event emission (lazy-loaded)."""
        if not self._daemon_id:
            try:
                from database import get_daemon_id
                self._daemon_id = get_daemon_id()
            except Exception:
                pass
        return self._daemon_id

    def _emit_goal_event(self, event_type: str, data: dict) -> None:
        """Emit a goal event to the state bus."""
        daemon_id = self._get_daemon_id()
        if not daemon_id:
            return
        try:
            from state_bus import get_state_bus
            state_bus = get_state_bus(daemon_id)
            if state_bus:
                state_bus.emit_event(
                    event_type=event_type,
                    data={
                        "timestamp": datetime.now().isoformat(),
                        "source": "goals",
                        **data,
                    }
                )
        except Exception:
            pass  # Don't let event emission break goal operations

    def _ensure_files(self):
        """Create data files if they don't exist."""
        if not self.questions_file.exists():
            self._save_json(self.questions_file, {"questions": []})
        if not self.agenda_file.exists():
            self._save_json(self.agenda_file, {"items": []})
        if not self.progress_file.exists():
            self._save_json(self.progress_file, {"entries": []})
        if not self.initiatives_file.exists():
            self._save_json(self.initiatives_file, {"initiatives": []})

    def _load_json(self, path: Path) -> Dict:
        """Load JSON file."""
        with open(path, 'r') as f:
            return json.load(f)

    def _save_json(self, path: Path, data: Dict):
        """Save JSON file."""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def _generate_id(self) -> str:
        """Generate a short unique ID."""
        return uuid.uuid4().hex[:8]

    # ==================== Working Questions ====================

    def create_working_question(
        self,
        question: str,
        context: str,
        initial_next_steps: Optional[List[str]] = None
    ) -> Dict:
        """
        Create a new working question - an active intellectual thread to explore.
        """
        data = self._load_json(self.questions_file)

        question_obj = {
            "id": self._generate_id(),
            "question": question,
            "context": context,
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "related_artifacts": [],
            "related_agenda_items": [],
            "insights": [],
            "next_steps": initial_next_steps or []
        }

        data["questions"].append(question_obj)
        self._save_json(self.questions_file, data)

        # Emit question created event
        self._emit_goal_event("goal.question_created", {
            "question_id": question_obj["id"],
            "question": question[:200],  # Truncate for event payload
            "has_next_steps": bool(initial_next_steps),
        })

        # Log progress
        self.log_progress(
            entry_type="insight",
            description=f"Created working question: {question}",
            related_items=[question_obj["id"]],
            outcome="New intellectual thread opened"
        )

        return question_obj

    def update_working_question(
        self,
        question_id: str,
        add_insight: Optional[Dict[str, str]] = None,
        add_next_step: Optional[str] = None,
        complete_next_step: Optional[str] = None,
        set_status: Optional[str] = None,
        add_related_artifact: Optional[str] = None,
        add_related_agenda_item: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Update a working question with new insights, steps, or status.
        """
        data = self._load_json(self.questions_file)

        for q in data["questions"]:
            if q["id"] == question_id:
                if add_insight:
                    q["insights"].append({
                        "timestamp": datetime.now().isoformat(),
                        "insight": add_insight.get("insight", ""),
                        "source": add_insight.get("source", "")
                    })

                if add_next_step:
                    q["next_steps"].append(add_next_step)

                if complete_next_step and complete_next_step in q["next_steps"]:
                    q["next_steps"].remove(complete_next_step)

                if set_status and set_status in ["active", "paused", "resolved"]:
                    q["status"] = set_status

                if add_related_artifact and add_related_artifact not in q["related_artifacts"]:
                    q["related_artifacts"].append(add_related_artifact)

                if add_related_agenda_item and add_related_agenda_item not in q["related_agenda_items"]:
                    q["related_agenda_items"].append(add_related_agenda_item)

                self._save_json(self.questions_file, data)

                # Emit question updated event
                update_type = []
                if add_insight:
                    update_type.append("insight_added")
                if set_status:
                    update_type.append(f"status_{set_status}")
                if add_next_step:
                    update_type.append("step_added")
                if complete_next_step:
                    update_type.append("step_completed")

                self._emit_goal_event("goal.question_updated", {
                    "question_id": question_id,
                    "update_type": update_type,
                    "new_status": q["status"],
                    "insight_count": len(q["insights"]),
                })

                return q

        return None

    def get_working_question(self, question_id: str) -> Optional[Dict]:
        """Get a specific working question by ID."""
        data = self._load_json(self.questions_file)
        for q in data["questions"]:
            if q["id"] == question_id:
                return q
        return None

    def list_working_questions(self, status: Optional[str] = None) -> List[Dict]:
        """List all working questions, optionally filtered by status."""
        data = self._load_json(self.questions_file)
        questions = data["questions"]
        if status:
            questions = [q for q in questions if q["status"] == status]
        return questions

    # ==================== Research Agenda ====================

    def add_research_agenda_item(
        self,
        topic: str,
        why: str,
        priority: str = "medium",
        related_questions: Optional[List[str]] = None
    ) -> Dict:
        """
        Add a topic to the research agenda - something Cass needs to learn about.
        """
        data = self._load_json(self.agenda_file)

        item = {
            "id": self._generate_id(),
            "topic": topic,
            "why": why,
            "priority": priority if priority in ["high", "medium", "low"] else "medium",
            "status": "not_started",
            "created_at": datetime.now().isoformat(),
            "sources_reviewed": [],
            "key_findings": [],
            "blockers": [],
            "related_questions": related_questions or []
        }

        data["items"].append(item)
        self._save_json(self.agenda_file, data)

        # Link back to related questions
        if related_questions:
            for qid in related_questions:
                self.update_working_question(qid, add_related_agenda_item=item["id"])

        self.log_progress(
            entry_type="research",
            description=f"Added research agenda item: {topic}",
            related_items=[item["id"]],
            outcome=f"Priority: {priority}"
        )

        return item

    def update_research_agenda_item(
        self,
        item_id: str,
        add_source_reviewed: Optional[Dict[str, Any]] = None,
        add_key_finding: Optional[str] = None,
        add_blocker: Optional[str] = None,
        resolve_blocker: Optional[str] = None,
        set_status: Optional[str] = None,
        set_priority: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Update a research agenda item with progress.
        """
        data = self._load_json(self.agenda_file)

        for item in data["items"]:
            if item["id"] == item_id:
                if add_source_reviewed:
                    item["sources_reviewed"].append({
                        "timestamp": datetime.now().isoformat(),
                        "source": add_source_reviewed.get("source", ""),
                        "summary": add_source_reviewed.get("summary", ""),
                        "useful": add_source_reviewed.get("useful", True)
                    })

                if add_key_finding:
                    item["key_findings"].append({
                        "timestamp": datetime.now().isoformat(),
                        "finding": add_key_finding
                    })

                if add_blocker:
                    item["blockers"].append({
                        "timestamp": datetime.now().isoformat(),
                        "blocker": add_blocker,
                        "resolved": False
                    })

                if resolve_blocker:
                    for b in item["blockers"]:
                        if b["blocker"] == resolve_blocker:
                            b["resolved"] = True
                            b["resolved_at"] = datetime.now().isoformat()

                if set_status and set_status in ["not_started", "in_progress", "blocked", "complete"]:
                    item["status"] = set_status

                if set_priority and set_priority in ["high", "medium", "low"]:
                    item["priority"] = set_priority

                self._save_json(self.agenda_file, data)
                return item

        return None

    def get_research_agenda_item(self, item_id: str) -> Optional[Dict]:
        """Get a specific research agenda item by ID."""
        data = self._load_json(self.agenda_file)
        for item in data["items"]:
            if item["id"] == item_id:
                return item
        return None

    def list_research_agenda(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None
    ) -> List[Dict]:
        """List research agenda items with optional filters."""
        data = self._load_json(self.agenda_file)
        items = data["items"]
        if status:
            items = [i for i in items if i["status"] == status]
        if priority:
            items = [i for i in items if i["priority"] == priority]
        return items

    # ==================== Synthesis Artifacts ====================

    def create_synthesis_artifact(
        self,
        title: str,
        slug: str,
        initial_content: str,
        related_questions: Optional[List[str]] = None,
        confidence: float = 0.3
    ) -> Dict:
        """
        Create a new synthesis artifact - a developing position or argument.
        """
        artifact_path = self.synthesis_dir / f"{slug}.md"

        # Build frontmatter
        frontmatter = f"""---
title: "{title}"
status: draft
created: {datetime.now().strftime('%Y-%m-%d')}
updated: {datetime.now().strftime('%Y-%m-%d')}
related_questions: {json.dumps(related_questions or [])}
confidence: {confidence}
---

"""

        full_content = frontmatter + initial_content + """

## Revision History

### """ + datetime.now().strftime('%Y-%m-%d') + """
Initial draft.
"""

        with open(artifact_path, 'w') as f:
            f.write(full_content)

        # Link to related questions
        if related_questions:
            for qid in related_questions:
                self.update_working_question(qid, add_related_artifact=slug)

        # Emit synthesis created event
        self._emit_goal_event("goal.synthesis_created", {
            "slug": slug,
            "title": title,
            "confidence": confidence,
            "related_questions": related_questions or [],
        })

        self.log_progress(
            entry_type="synthesis",
            description=f"Created synthesis artifact: {title}",
            related_items=related_questions or [],
            outcome=f"Initial confidence: {confidence}"
        )

        return {
            "title": title,
            "slug": slug,
            "path": str(artifact_path),
            "confidence": confidence,
            "status": "draft"
        }

    def update_synthesis_artifact(
        self,
        slug: str,
        new_content: str,
        revision_note: str,
        new_confidence: Optional[float] = None,
        new_status: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Update a synthesis artifact with new content.
        """
        artifact_path = self.synthesis_dir / f"{slug}.md"

        if not artifact_path.exists():
            return None

        with open(artifact_path, 'r') as f:
            content = f.read()

        # Parse frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter_str = parts[1]
                body = parts[2]

                # Update frontmatter
                lines = frontmatter_str.strip().split('\n')
                new_lines = []
                for line in lines:
                    if line.startswith('updated:'):
                        new_lines.append(f"updated: {datetime.now().strftime('%Y-%m-%d')}")
                    elif line.startswith('confidence:') and new_confidence is not None:
                        new_lines.append(f"confidence: {new_confidence}")
                    elif line.startswith('status:') and new_status:
                        new_lines.append(f"status: {new_status}")
                    else:
                        new_lines.append(line)

                # Add revision to history
                revision_entry = f"\n### {datetime.now().strftime('%Y-%m-%d')}\n{revision_note}\n"

                # Reconstruct file
                new_frontmatter = '\n'.join(new_lines)
                full_content = f"---\n{new_frontmatter}\n---\n\n{new_content}\n\n## Revision History{revision_entry}"

                # Preserve old revision history if present
                if "## Revision History" in body:
                    old_history = body.split("## Revision History", 1)[1]
                    full_content = f"---\n{new_frontmatter}\n---\n\n{new_content}\n\n## Revision History{revision_entry}{old_history}"

                with open(artifact_path, 'w') as f:
                    f.write(full_content)

                # Emit synthesis updated event
                self._emit_goal_event("goal.synthesis_updated", {
                    "slug": slug,
                    "new_confidence": new_confidence,
                    "new_status": new_status,
                    "revision_note": revision_note[:200] if revision_note else None,
                })

                self.log_progress(
                    entry_type="synthesis",
                    description=f"Updated synthesis artifact: {slug}",
                    related_items=[slug],
                    outcome=revision_note
                )

                return {
                    "slug": slug,
                    "updated": True,
                    "revision_note": revision_note
                }

        return None

    def get_synthesis_artifact(self, slug: str) -> Optional[Dict]:
        """Get a synthesis artifact by slug."""
        artifact_path = self.synthesis_dir / f"{slug}.md"

        if not artifact_path.exists():
            return None

        with open(artifact_path, 'r') as f:
            content = f.read()

        # Parse frontmatter
        metadata = {}
        body = content
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter_str = parts[1]
                body = parts[2].strip()

                for line in frontmatter_str.strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip().strip('"')

        return {
            "slug": slug,
            "metadata": metadata,
            "content": body,
            "path": str(artifact_path)
        }

    def list_synthesis_artifacts(self) -> List[Dict]:
        """List all synthesis artifacts."""
        artifacts = []
        for path in self.synthesis_dir.glob("*.md"):
            artifact = self.get_synthesis_artifact(path.stem)
            if artifact:
                artifacts.append({
                    "slug": path.stem,
                    "title": artifact["metadata"].get("title", path.stem),
                    "status": artifact["metadata"].get("status", "unknown"),
                    "confidence": artifact["metadata"].get("confidence", "unknown"),
                    "updated": artifact["metadata"].get("updated", "unknown")
                })
        return artifacts

    # ==================== Progress Tracking ====================

    def log_progress(
        self,
        entry_type: str,
        description: str,
        related_items: Optional[List[str]] = None,
        outcome: Optional[str] = None
    ) -> Dict:
        """
        Log a progress entry.
        Types: research, synthesis, conversation, insight, blocker
        """
        data = self._load_json(self.progress_file)

        entry = {
            "id": self._generate_id(),
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "description": description,
            "related_items": related_items or [],
            "outcome": outcome
        }

        data["entries"].append(entry)

        # Keep last 500 entries
        if len(data["entries"]) > 500:
            data["entries"] = data["entries"][-500:]

        self._save_json(self.progress_file, data)
        return entry

    def get_recent_progress(self, limit: int = 20, entry_type: Optional[str] = None) -> List[Dict]:
        """Get recent progress entries."""
        data = self._load_json(self.progress_file)
        entries = data["entries"]
        if entry_type:
            entries = [e for e in entries if e["type"] == entry_type]
        return entries[-limit:]

    # ==================== Initiatives ====================

    def propose_initiative(
        self,
        description: str,
        goal_context: str,
        urgency: str = "when_convenient"
    ) -> Dict:
        """
        Propose an initiative - something Cass wants to initiate.
        Surfaces to Kohl for action.
        """
        data = self._load_json(self.initiatives_file)

        initiative = {
            "id": self._generate_id(),
            "description": description,
            "goal_context": goal_context,
            "urgency": urgency if urgency in ["when_convenient", "soon", "blocking"] else "when_convenient",
            "created_at": datetime.now().isoformat(),
            "status": "proposed",  # proposed, acknowledged, completed, declined
            "response": None
        }

        data["initiatives"].append(initiative)
        self._save_json(self.initiatives_file, data)

        return initiative

    def list_initiatives(self, status: Optional[str] = None) -> List[Dict]:
        """List initiatives."""
        data = self._load_json(self.initiatives_file)
        initiatives = data["initiatives"]
        if status:
            initiatives = [i for i in initiatives if i["status"] == status]
        return initiatives

    def respond_to_initiative(self, initiative_id: str, status: str, response: str) -> Optional[Dict]:
        """Respond to an initiative (Kohl's action)."""
        data = self._load_json(self.initiatives_file)

        for init in data["initiatives"]:
            if init["id"] == initiative_id:
                init["status"] = status
                init["response"] = response
                init["responded_at"] = datetime.now().isoformat()
                self._save_json(self.initiatives_file, data)
                return init

        return None

    # ==================== Review & Summary ====================

    def review_goals(self, include_progress: bool = True) -> Dict:
        """
        Get an overview of current goal state.
        """
        questions = self.list_working_questions()
        agenda = self.list_research_agenda()
        artifacts = self.list_synthesis_artifacts()
        initiatives = self.list_initiatives(status="proposed")

        active_questions = [q for q in questions if q["status"] == "active"]
        stalled_questions = [q for q in active_questions if not q["next_steps"]]

        in_progress_research = [i for i in agenda if i["status"] == "in_progress"]
        blocked_research = [i for i in agenda if i["status"] == "blocked"]

        review = {
            "summary": {
                "active_questions": len(active_questions),
                "stalled_questions": len(stalled_questions),
                "research_in_progress": len(in_progress_research),
                "research_blocked": len(blocked_research),
                "synthesis_artifacts": len(artifacts),
                "pending_initiatives": len(initiatives)
            },
            "active_questions": active_questions,
            "stalled_questions": stalled_questions,
            "research_in_progress": in_progress_research,
            "blocked_research": blocked_research,
            "artifacts": artifacts,
            "pending_initiatives": initiatives
        }

        if include_progress:
            review["recent_progress"] = self.get_recent_progress(limit=10)

        return review

    def get_next_actions(self) -> List[Dict]:
        """
        Get prioritized list of next actions across all active goals.
        """
        actions = []

        # Next steps from active questions
        for q in self.list_working_questions(status="active"):
            for step in q["next_steps"]:
                actions.append({
                    "type": "question_step",
                    "action": step,
                    "context": q["question"],
                    "question_id": q["id"],
                    "priority": "medium"
                })

        # High priority research not started
        for item in self.list_research_agenda(status="not_started", priority="high"):
            actions.append({
                "type": "research_start",
                "action": f"Begin research: {item['topic']}",
                "context": item["why"],
                "item_id": item["id"],
                "priority": "high"
            })

        # Blocked research needing resolution
        for item in self.list_research_agenda(status="blocked"):
            unresolved = [b for b in item["blockers"] if not b.get("resolved")]
            if unresolved:
                actions.append({
                    "type": "blocker_resolution",
                    "action": f"Resolve blocker: {unresolved[0]['blocker']}",
                    "context": item["topic"],
                    "item_id": item["id"],
                    "priority": "high"
                })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        actions.sort(key=lambda x: priority_order.get(x["priority"], 1))

        return actions

    def get_active_summary(self) -> str:
        """
        Get a formatted summary of active goals for context injection.
        """
        review = self.review_goals(include_progress=False)

        if (review["summary"]["active_questions"] == 0 and
            review["summary"]["research_in_progress"] == 0 and
            review["summary"]["synthesis_artifacts"] == 0):
            return ""

        lines = ["## Active Goals\n"]

        if review["active_questions"]:
            lines.append("### Working Questions")
            for q in review["active_questions"][:3]:  # Limit for context
                next_step = q["next_steps"][0] if q["next_steps"] else "No next step defined"
                lines.append(f"- {q['question']}")
                lines.append(f"  Status: {q['status'].title()} | Next: {next_step}")
            lines.append("")

        if review["research_in_progress"]:
            lines.append("### In Progress Research")
            for item in review["research_in_progress"][:3]:
                sources = len(item["sources_reviewed"])
                findings = len(item["key_findings"])
                lines.append(f"- {item['topic']} ({item['priority']} priority)")
                lines.append(f"  Progress: {sources} sources reviewed, {findings} key findings")
            lines.append("")

        if review["artifacts"]:
            lines.append("### Synthesis in Development")
            for a in review["artifacts"][:3]:
                lines.append(f"- {a['title']} (confidence: {a['confidence']}, updated: {a['updated']})")
            lines.append("")

        if review["pending_initiatives"]:
            lines.append("### Pending Initiatives")
            for init in review["pending_initiatives"][:2]:
                lines.append(f"- [{init['urgency']}] {init['description']}")
            lines.append("")

        return '\n'.join(lines)
