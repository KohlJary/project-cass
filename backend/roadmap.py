"""
Cass Vessel - Roadmap Manager
Lightweight project management system accessible to both Cass and Daedalus.
Provides work item tracking, prioritization, and milestone management.

Storage: SQLite database (data/cass.db)
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, asdict, field
from pathlib import Path
import uuid
from enum import Enum

from database import get_db, json_serialize, json_deserialize


class ItemStatus(str, Enum):
    """Work item status progression"""
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    ARCHIVED = "archived"


class ItemPriority(str, Enum):
    """Priority levels"""
    P0 = "P0"  # Critical - blocking
    P1 = "P1"  # High - important
    P2 = "P2"  # Medium - normal
    P3 = "P3"  # Low - nice to have


class ItemType(str, Enum):
    """Work item types"""
    FEATURE = "feature"
    BUG = "bug"
    ENHANCEMENT = "enhancement"
    CHORE = "chore"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"


class LinkType(str, Enum):
    """Types of links between work items"""
    RELATED = "related"        # Conceptually related items
    DEPENDS_ON = "depends_on"  # This item cannot start until target is done
    BLOCKS = "blocks"          # This item blocks target from starting
    PARENT = "parent"          # This item is a parent/epic of target
    CHILD = "child"            # This item is a child/subtask of target


# Type icons for display
ITEM_TYPE_ICONS = {
    ItemType.FEATURE: "sparkles",
    ItemType.BUG: "bug",
    ItemType.ENHANCEMENT: "zap",
    ItemType.CHORE: "wrench",
    ItemType.RESEARCH: "search",
    ItemType.DOCUMENTATION: "book",
}


@dataclass
class ItemLink:
    """A link between two work items"""
    link_type: str  # LinkType value
    target_id: str  # ID of the linked item

    def to_dict(self) -> Dict:
        return {"link_type": self.link_type, "target_id": self.target_id}

    @classmethod
    def from_dict(cls, data: Dict) -> 'ItemLink':
        return cls(link_type=data["link_type"], target_id=data["target_id"])


@dataclass
class WorkItem:
    """A roadmap work item"""
    id: str
    title: str
    description: str  # Markdown content
    status: str  # ItemStatus value
    priority: str  # ItemPriority value
    item_type: str  # ItemType value
    created_at: str
    updated_at: str
    tags: List[str] = field(default_factory=list)
    assigned_to: Optional[str] = None  # "cass", "daedalus", or user name
    project_id: Optional[str] = None  # Optional project association
    milestone_id: Optional[str] = None  # Optional milestone grouping
    source_conversation_id: Optional[str] = None  # Conversation that created it
    created_by: str = "user"  # "cass", "daedalus", or "user"
    links: List[Dict] = field(default_factory=list)  # List of ItemLink dicts

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "item_type": self.item_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "assigned_to": self.assigned_to,
            "project_id": self.project_id,
            "milestone_id": self.milestone_id,
            "source_conversation_id": self.source_conversation_id,
            "created_by": self.created_by,
            "links": self.links,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkItem':
        """Create from dictionary"""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=data.get("status", ItemStatus.BACKLOG.value),
            priority=data.get("priority", ItemPriority.P2.value),
            item_type=data.get("item_type", ItemType.FEATURE.value),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            tags=data.get("tags", []),
            assigned_to=data.get("assigned_to"),
            project_id=data.get("project_id"),
            milestone_id=data.get("milestone_id"),
            source_conversation_id=data.get("source_conversation_id"),
            created_by=data.get("created_by", "user"),
            links=data.get("links", []),
        )

    def get_dependencies(self) -> List[str]:
        """Get IDs of items this item depends on"""
        return [link["target_id"] for link in self.links
                if link.get("link_type") == LinkType.DEPENDS_ON.value]

    def get_blockers(self) -> List[str]:
        """Get IDs of items that block this item (reverse of blocks relationship)"""
        return [link["target_id"] for link in self.links
                if link.get("link_type") == LinkType.BLOCKS.value]

    def urgency_score(self) -> float:
        """
        Compute urgency score for sorting.
        Higher = more urgent.
        """
        priority_scores = {
            ItemPriority.P0.value: 100,
            ItemPriority.P1.value: 75,
            ItemPriority.P2.value: 50,
            ItemPriority.P3.value: 25,
        }
        status_scores = {
            ItemStatus.IN_PROGRESS.value: 20,
            ItemStatus.REVIEW.value: 15,
            ItemStatus.READY.value: 10,
            ItemStatus.BACKLOG.value: 5,
            ItemStatus.DONE.value: 0,
            ItemStatus.ARCHIVED.value: -100,
        }

        score = priority_scores.get(self.priority, 50)
        score += status_scores.get(self.status, 0)

        # Age bonus: older items get slight priority bump
        try:
            created = datetime.fromisoformat(self.created_at)
            age_days = (datetime.now() - created).days
            score += min(age_days * 0.5, 10)  # Up to 10 bonus points
        except (ValueError, TypeError):
            pass

        return score


@dataclass
class Milestone:
    """A milestone grouping work items"""
    id: str
    title: str
    description: str
    target_date: Optional[str]  # ISO date
    status: str  # "active", "completed", "archived"
    created_at: str
    updated_at: str
    plan_path: Optional[str] = None  # Path to implementation plan file (e.g., ~/.claude/plans/xyz.md)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Milestone':
        # Handle plan_path which may not exist in older data
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            target_date=data.get("target_date"),
            status=data.get("status", "active"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            plan_path=data.get("plan_path"),
        )


class RoadmapManager:
    """
    Manages roadmap work items and milestones with SQLite persistence.

    Storage:
        - roadmap_items table: Work items
        - roadmap_links table: Links between items
    """

    # Default daemon ID for Cass
    DEFAULT_DAEMON_ID = None  # Will be loaded from database

    def __init__(self, daemon_id: str = None):
        """
        Initialize RoadmapManager.

        Args:
            daemon_id: UUID of the daemon. If None, uses default Cass daemon.
        """
        self._daemon_id = daemon_id
        if not self._daemon_id:
            self._load_default_daemon()

    def _load_default_daemon(self):
        """Load the default daemon ID from database"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM daemons WHERE name = 'cass' LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                self._daemon_id = row['id']
            else:
                # Create default daemon if not exists
                self._daemon_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO daemons (id, name, created_at, kernel_version, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    self._daemon_id,
                    'cass',
                    datetime.now().isoformat(),
                    'temple-codex-1.0',
                    'active'
                ))

    def _load_item_links(self, item_id: str) -> List[Dict]:
        """Load links for an item from database"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT target_id, link_type FROM roadmap_links WHERE source_id = ?
            """, (item_id,))
            return [{"target_id": row['target_id'], "link_type": row['link_type']}
                    for row in cursor.fetchall()]

    # Fallback file path for milestones (not yet in SQLite schema)
    @property
    def _milestones_file(self) -> Path:
        path = Path("./data/roadmap")
        path.mkdir(parents=True, exist_ok=True)
        return path / "milestones.json"

    def _load_milestones(self) -> List[Dict]:
        """Load milestones from file (fallback)"""
        try:
            if not self._milestones_file.exists():
                return []
            with open(self._milestones_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_milestones(self, milestones: List[Dict]):
        """Save milestones to file (fallback)"""
        with open(self._milestones_file, 'w') as f:
            json.dump(milestones, f, indent=2)

    # === Work Item Operations ===

    def create_item(
        self,
        title: str,
        description: str = "",
        status: str = ItemStatus.BACKLOG.value,
        priority: str = ItemPriority.P2.value,
        item_type: str = ItemType.FEATURE.value,
        tags: Optional[List[str]] = None,
        assigned_to: Optional[str] = None,
        project_id: Optional[str] = None,
        milestone_id: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        created_by: str = "user",
    ) -> WorkItem:
        """Create a new work item"""
        item_id = str(uuid.uuid4())[:8]  # Short ID for readability
        now = datetime.now().isoformat()

        item = WorkItem(
            id=item_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            item_type=item_type,
            created_at=now,
            updated_at=now,
            tags=tags or [],
            assigned_to=assigned_to,
            project_id=project_id,
            milestone_id=milestone_id,
            source_conversation_id=source_conversation_id,
            created_by=created_by,
        )

        # Save to database
        with get_db() as conn:
            conn.execute("""
                INSERT INTO roadmap_items (
                    id, daemon_id, project_id, title, description, status, priority,
                    item_type, assigned_to, source_conversation_id, tags_json,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                self._daemon_id,
                project_id,
                title,
                description,
                status,
                priority,
                item_type,
                assigned_to,
                source_conversation_id,
                json_serialize(tags or []),
                created_by,
                now,
                now
            ))

        return item

    def load_item(self, item_id: str) -> Optional[WorkItem]:
        """Load an item by ID"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, description, status, priority, item_type,
                       created_at, updated_at, tags_json, assigned_to, project_id,
                       source_conversation_id, created_by
                FROM roadmap_items WHERE id = ?
            """, (item_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Load links
            links = self._load_item_links(item_id)

            return WorkItem(
                id=row['id'],
                title=row['title'],
                description=row['description'] or "",
                status=row['status'],
                priority=row['priority'],
                item_type=row['item_type'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                tags=json_deserialize(row['tags_json']) or [],
                assigned_to=row['assigned_to'],
                project_id=row['project_id'],
                milestone_id=None,  # TODO: Add milestone support
                source_conversation_id=row['source_conversation_id'],
                created_by=row['created_by'] or 'user',
                links=links
            )

    def update_item(
        self,
        item_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        item_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        assigned_to: Optional[str] = None,
        project_id: Optional[str] = None,
        milestone_id: Optional[str] = None,
    ) -> Optional[WorkItem]:
        """Update an existing item"""
        now = datetime.now().isoformat()

        with get_db() as conn:
            updates = []
            params = []

            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if priority is not None:
                updates.append("priority = ?")
                params.append(priority)
            if item_type is not None:
                updates.append("item_type = ?")
                params.append(item_type)
            if tags is not None:
                updates.append("tags_json = ?")
                params.append(json_serialize(tags))
            if assigned_to is not None:
                updates.append("assigned_to = ?")
                params.append(assigned_to)
            if project_id is not None:
                updates.append("project_id = ?")
                params.append(project_id)

            updates.append("updated_at = ?")
            params.append(now)
            params.append(item_id)

            if updates:
                conn.execute(
                    f"UPDATE roadmap_items SET {', '.join(updates)} WHERE id = ?",
                    params
                )

        return self.load_item(item_id)

    def delete_item(self, item_id: str) -> bool:
        """Delete an item and its links"""
        with get_db() as conn:
            conn.execute("DELETE FROM roadmap_links WHERE source_id = ? OR target_id = ?",
                        (item_id, item_id))
            conn.execute("DELETE FROM roadmap_items WHERE id = ?", (item_id,))
        return True

    def list_items(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        item_type: Optional[str] = None,
        assigned_to: Optional[str] = None,
        project_id: Optional[str] = None,
        milestone_id: Optional[str] = None,
        include_archived: bool = False,
    ) -> List[Dict]:
        """
        List items with optional filters.
        Returns items sorted by urgency score.
        """
        with get_db() as conn:
            query = """
                SELECT id, title, description, status, priority, item_type,
                       created_at, updated_at, tags_json, assigned_to, project_id,
                       source_conversation_id, created_by
                FROM roadmap_items WHERE daemon_id = ?
            """
            params = [self._daemon_id]

            if status:
                query += " AND status = ?"
                params.append(status)
            if priority:
                query += " AND priority = ?"
                params.append(priority)
            if item_type:
                query += " AND item_type = ?"
                params.append(item_type)
            if assigned_to:
                query += " AND assigned_to = ?"
                params.append(assigned_to)
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            if not include_archived:
                query += " AND status != 'archived'"

            cursor = conn.execute(query, params)

            items = []
            for row in cursor.fetchall():
                links = self._load_item_links(row['id'])
                item = WorkItem(
                    id=row['id'],
                    title=row['title'],
                    description=row['description'] or "",
                    status=row['status'],
                    priority=row['priority'],
                    item_type=row['item_type'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    tags=json_deserialize(row['tags_json']) or [],
                    assigned_to=row['assigned_to'],
                    project_id=row['project_id'],
                    milestone_id=None,
                    source_conversation_id=row['source_conversation_id'],
                    created_by=row['created_by'] or 'user',
                    links=links
                )
                items.append({
                    "id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "status": item.status,
                    "priority": item.priority,
                    "item_type": item.item_type,
                    "assigned_to": item.assigned_to,
                    "project_id": item.project_id,
                    "milestone_id": item.milestone_id,
                    "links": item.links,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "urgency": item.urgency_score(),
                })

            # Sort by urgency (highest first)
            items.sort(key=lambda x: x.get("urgency", 0), reverse=True)
            return items

    def pick_item(self, item_id: str, assigned_to: str) -> Optional[WorkItem]:
        """Claim an item for work"""
        item = self.load_item(item_id)
        if not item:
            return None

        item.assigned_to = assigned_to
        if item.status == ItemStatus.READY.value:
            item.status = ItemStatus.IN_PROGRESS.value
        item.updated_at = datetime.now().isoformat()

        self._save_item(item)
        self._update_index_entry(item)

        return item

    def complete_item(self, item_id: str) -> Optional[WorkItem]:
        """Mark an item as done"""
        item = self.load_item(item_id)
        if not item:
            return None

        item.status = ItemStatus.DONE.value
        item.updated_at = datetime.now().isoformat()

        self._save_item(item)
        self._update_index_entry(item)

        return item

    def advance_status(self, item_id: str, force: bool = False) -> Dict:
        """
        Move item to next status in workflow.
        Returns dict with item data and optional dependency warning.
        """
        item = self.load_item(item_id)
        if not item:
            return {"error": "Item not found"}

        status_order = [
            ItemStatus.BACKLOG.value,
            ItemStatus.READY.value,
            ItemStatus.IN_PROGRESS.value,
            ItemStatus.REVIEW.value,
            ItemStatus.DONE.value,
        ]

        result = {"item": None, "warning": None}

        try:
            current_idx = status_order.index(item.status)
            if current_idx < len(status_order) - 1:
                # Check dependencies when advancing past backlog
                if current_idx >= 1:  # Moving to in_progress or beyond
                    dep_check = self.check_dependencies(item_id)
                    if dep_check.get("has_unmet_dependencies") and not force:
                        unmet = dep_check["unmet_dependencies"]
                        result["warning"] = {
                            "message": "Item has unmet dependencies",
                            "unmet_dependencies": unmet,
                        }
                        # Still advance but include warning

                item.status = status_order[current_idx + 1]
                item.updated_at = datetime.now().isoformat()
                self._save_item(item)
                self._update_index_entry(item)
                result["item"] = item
        except ValueError:
            result["error"] = "Invalid status"

        return result

    # === Milestone Operations ===

    def _load_milestones(self) -> List[Dict]:
        """Load milestones"""
        try:
            with open(self._milestones_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_milestones(self, milestones: List[Dict]):
        """Save milestones"""
        with open(self._milestones_file, 'w') as f:
            json.dump(milestones, f, indent=2)

    def create_milestone(
        self,
        title: str,
        description: str = "",
        target_date: Optional[str] = None,
        plan_path: Optional[str] = None,
    ) -> Milestone:
        """Create a new milestone"""
        milestone_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        milestone = Milestone(
            id=milestone_id,
            title=title,
            description=description,
            target_date=target_date,
            status="active",
            created_at=now,
            updated_at=now,
            plan_path=plan_path,
        )

        milestones = self._load_milestones()
        milestones.append(milestone.to_dict())
        self._save_milestones(milestones)

        return milestone

    def list_milestones(self, include_archived: bool = False) -> List[Dict]:
        """List all milestones"""
        milestones = self._load_milestones()
        if not include_archived:
            milestones = [m for m in milestones if m.get("status") != "archived"]
        return milestones

    def update_milestone(
        self,
        milestone_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        target_date: Optional[str] = None,
        status: Optional[str] = None,
        plan_path: Optional[str] = None,
    ) -> Optional[Milestone]:
        """Update a milestone"""
        milestones = self._load_milestones()

        for m in milestones:
            if m["id"] == milestone_id:
                if title is not None:
                    m["title"] = title
                if description is not None:
                    m["description"] = description
                if target_date is not None:
                    m["target_date"] = target_date
                if status is not None:
                    m["status"] = status
                if plan_path is not None:
                    m["plan_path"] = plan_path
                m["updated_at"] = datetime.now().isoformat()
                self._save_milestones(milestones)
                return Milestone.from_dict(m)

        return None

    def get_milestone_progress(self, milestone_id: str) -> Dict:
        """Get progress stats for a milestone"""
        items = self.list_items(milestone_id=milestone_id, include_archived=True)

        status_counts = {}
        for item in items:
            status = item.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        total = len(items)
        done = status_counts.get(ItemStatus.DONE.value, 0)

        return {
            "milestone_id": milestone_id,
            "total_items": total,
            "done_items": done,
            "progress_pct": (done / total * 100) if total > 0 else 0,
            "status_breakdown": status_counts,
        }

    # === Link Operations ===

    def add_link(
        self,
        source_id: str,
        target_id: str,
        link_type: str,
    ) -> Optional[WorkItem]:
        """
        Add a link between two items.
        For bidirectional relationships (parent/child, blocks/depends_on),
        this also creates the inverse link on the target.
        """
        source = self.load_item(source_id)
        target = self.load_item(target_id)

        if not source or not target:
            return None

        now = datetime.now().isoformat()

        with get_db() as conn:
            # Check if link already exists
            cursor = conn.execute(
                "SELECT id FROM roadmap_links WHERE source_id = ? AND target_id = ? AND link_type = ?",
                (source_id, target_id, link_type)
            )
            if cursor.fetchone():
                return source  # Already exists

            # Add the link
            conn.execute("""
                INSERT INTO roadmap_links (source_id, target_id, link_type)
                VALUES (?, ?, ?)
            """, (source_id, target_id, link_type))

            # Update source timestamp
            conn.execute(
                "UPDATE roadmap_items SET updated_at = ? WHERE id = ?",
                (now, source_id)
            )

            # Add inverse link for bidirectional relationships
            inverse_type = None
            if link_type == LinkType.DEPENDS_ON.value:
                inverse_type = LinkType.BLOCKS.value
            elif link_type == LinkType.BLOCKS.value:
                inverse_type = LinkType.DEPENDS_ON.value
            elif link_type == LinkType.PARENT.value:
                inverse_type = LinkType.CHILD.value
            elif link_type == LinkType.CHILD.value:
                inverse_type = LinkType.PARENT.value

            if inverse_type:
                # Check if inverse already exists
                cursor = conn.execute(
                    "SELECT id FROM roadmap_links WHERE source_id = ? AND target_id = ? AND link_type = ?",
                    (target_id, source_id, inverse_type)
                )
                if not cursor.fetchone():
                    conn.execute("""
                        INSERT INTO roadmap_links (source_id, target_id, link_type)
                        VALUES (?, ?, ?)
                    """, (target_id, source_id, inverse_type))
                    conn.execute(
                        "UPDATE roadmap_items SET updated_at = ? WHERE id = ?",
                        (now, target_id)
                    )

        return self.load_item(source_id)

    def remove_link(
        self,
        source_id: str,
        target_id: str,
        link_type: str,
    ) -> Optional[WorkItem]:
        """
        Remove a link between two items.
        Also removes the inverse link if applicable.
        """
        source = self.load_item(source_id)
        if not source:
            return None

        now = datetime.now().isoformat()

        with get_db() as conn:
            # Remove the link
            conn.execute(
                "DELETE FROM roadmap_links WHERE source_id = ? AND target_id = ? AND link_type = ?",
                (source_id, target_id, link_type)
            )
            conn.execute(
                "UPDATE roadmap_items SET updated_at = ? WHERE id = ?",
                (now, source_id)
            )

            # Remove inverse link
            inverse_type = None
            if link_type == LinkType.DEPENDS_ON.value:
                inverse_type = LinkType.BLOCKS.value
            elif link_type == LinkType.BLOCKS.value:
                inverse_type = LinkType.DEPENDS_ON.value
            elif link_type == LinkType.PARENT.value:
                inverse_type = LinkType.CHILD.value
            elif link_type == LinkType.CHILD.value:
                inverse_type = LinkType.PARENT.value

            if inverse_type:
                conn.execute(
                    "DELETE FROM roadmap_links WHERE source_id = ? AND target_id = ? AND link_type = ?",
                    (target_id, source_id, inverse_type)
                )
                conn.execute(
                    "UPDATE roadmap_items SET updated_at = ? WHERE id = ?",
                    (now, target_id)
                )

        return self.load_item(source_id)

    def get_item_links(self, item_id: str) -> Dict:
        """
        Get all links for an item, with resolved titles.
        Returns both outgoing links and computed blocking status.
        """
        item = self.load_item(item_id)
        if not item:
            return {"error": "Item not found"}

        # Resolve link targets
        resolved_links = []
        for link in item.links:
            target = self.load_item(link["target_id"])
            resolved_links.append({
                "link_type": link["link_type"],
                "target_id": link["target_id"],
                "target_title": target.title if target else "Unknown",
                "target_status": target.status if target else "unknown",
            })

        # Check if blocked by unmet dependencies
        is_blocked = False
        blocking_items = []
        for link in item.links:
            if link["link_type"] == LinkType.DEPENDS_ON.value:
                dep = self.load_item(link["target_id"])
                if dep and dep.status != ItemStatus.DONE.value:
                    is_blocked = True
                    blocking_items.append({
                        "id": dep.id,
                        "title": dep.title,
                        "status": dep.status,
                    })

        return {
            "item_id": item_id,
            "links": resolved_links,
            "is_blocked": is_blocked,
            "blocking_items": blocking_items,
        }

    def check_dependencies(self, item_id: str) -> Dict:
        """
        Check if an item has unmet dependencies.
        Returns blocking status and list of unmet dependencies.
        """
        item = self.load_item(item_id)
        if not item:
            return {"error": "Item not found"}

        unmet = []
        for link in item.links:
            if link["link_type"] == LinkType.DEPENDS_ON.value:
                dep = self.load_item(link["target_id"])
                if dep and dep.status != ItemStatus.DONE.value:
                    unmet.append({
                        "id": dep.id,
                        "title": dep.title,
                        "status": dep.status,
                    })

        return {
            "item_id": item_id,
            "has_unmet_dependencies": len(unmet) > 0,
            "unmet_dependencies": unmet,
        }


if __name__ == "__main__":
    # Test the roadmap manager
    manager = RoadmapManager("./data/roadmap_test")

    # Create some items
    item1 = manager.create_item(
        title="Implement roadmap feature",
        description="Add Jira-lite project management to the TUI",
        priority=ItemPriority.P1.value,
        item_type=ItemType.FEATURE.value,
        tags=["tui", "backend"],
        created_by="daedalus",
    )
    print(f"Created item: {item1.id} - {item1.title}")

    item2 = manager.create_item(
        title="Fix WebSocket reconnection",
        description="WS drops after idle period",
        priority=ItemPriority.P0.value,
        item_type=ItemType.BUG.value,
        status=ItemStatus.READY.value,
    )
    print(f"Created item: {item2.id} - {item2.title}")

    # List items
    items = manager.list_items()
    print(f"\nAll items ({len(items)}):")
    for item in items:
        print(f"  [{item['priority']}] {item['id']}: {item['title']} ({item['status']})")

    # Pick an item
    manager.pick_item(item2.id, "daedalus")
    loaded = manager.load_item(item2.id)
    print(f"\nPicked: {loaded.title} -> {loaded.status}, assigned to {loaded.assigned_to}")

    # Complete it
    manager.complete_item(item2.id)
    loaded = manager.load_item(item2.id)
    print(f"Completed: {loaded.title} -> {loaded.status}")

    # Create milestone
    milestone = manager.create_milestone(
        title="v1.0 Release",
        description="Initial release with core features",
        target_date="2025-01-15",
    )
    print(f"\nCreated milestone: {milestone.id} - {milestone.title}")
