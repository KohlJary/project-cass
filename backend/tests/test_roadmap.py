"""
Tests for roadmap.py - Roadmap and work item management.

Tests cover:
- Enum values (ItemStatus, ItemPriority, ItemType, LinkType)
- ItemLink dataclass
- WorkItem dataclass and methods
- Milestone dataclass
- RoadmapManager CRUD operations
- Milestone management
- Link operations
- Dependency checking
"""
import pytest
from datetime import datetime, timedelta

from roadmap import (
    ItemStatus, ItemPriority, ItemType, LinkType,
    ItemLink, WorkItem, Milestone, RoadmapManager,
    ITEM_TYPE_ICONS
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------

class TestItemStatus:
    """Tests for ItemStatus enum."""

    def test_status_values(self):
        """ItemStatus should have correct workflow values."""
        assert ItemStatus.BACKLOG.value == "backlog"
        assert ItemStatus.READY.value == "ready"
        assert ItemStatus.IN_PROGRESS.value == "in_progress"
        assert ItemStatus.REVIEW.value == "review"
        assert ItemStatus.DONE.value == "done"
        assert ItemStatus.ARCHIVED.value == "archived"


class TestItemPriority:
    """Tests for ItemPriority enum."""

    def test_priority_values(self):
        """ItemPriority should have P0-P3 values."""
        assert ItemPriority.P0.value == "P0"
        assert ItemPriority.P1.value == "P1"
        assert ItemPriority.P2.value == "P2"
        assert ItemPriority.P3.value == "P3"


class TestItemType:
    """Tests for ItemType enum."""

    def test_type_values(self):
        """ItemType should have correct values."""
        assert ItemType.FEATURE.value == "feature"
        assert ItemType.BUG.value == "bug"
        assert ItemType.ENHANCEMENT.value == "enhancement"
        assert ItemType.CHORE.value == "chore"
        assert ItemType.RESEARCH.value == "research"
        assert ItemType.DOCUMENTATION.value == "documentation"

    def test_type_icons_mapping(self):
        """Each ItemType should have an icon."""
        for item_type in ItemType:
            assert item_type in ITEM_TYPE_ICONS


class TestLinkType:
    """Tests for LinkType enum."""

    def test_link_values(self):
        """LinkType should have relationship values."""
        assert LinkType.RELATED.value == "related"
        assert LinkType.DEPENDS_ON.value == "depends_on"
        assert LinkType.BLOCKS.value == "blocks"
        assert LinkType.PARENT.value == "parent"
        assert LinkType.CHILD.value == "child"


# ---------------------------------------------------------------------------
# ItemLink Tests
# ---------------------------------------------------------------------------

class TestItemLink:
    """Tests for ItemLink dataclass."""

    def test_item_link_creation(self):
        """Should create ItemLink with required fields."""
        link = ItemLink(link_type="depends_on", target_id="item-123")
        assert link.link_type == "depends_on"
        assert link.target_id == "item-123"

    def test_item_link_to_dict(self):
        """to_dict should serialize correctly."""
        link = ItemLink(link_type="blocks", target_id="item-456")
        d = link.to_dict()
        assert d == {"link_type": "blocks", "target_id": "item-456"}

    def test_item_link_from_dict(self):
        """from_dict should deserialize correctly."""
        data = {"link_type": "parent", "target_id": "item-789"}
        link = ItemLink.from_dict(data)
        assert link.link_type == "parent"
        assert link.target_id == "item-789"


# ---------------------------------------------------------------------------
# WorkItem Tests
# ---------------------------------------------------------------------------

class TestWorkItem:
    """Tests for WorkItem dataclass."""

    def test_work_item_creation(self):
        """Should create WorkItem with all fields."""
        now = datetime.now().isoformat()
        item = WorkItem(
            id="item-abc",
            title="Test Item",
            description="Description here",
            status=ItemStatus.BACKLOG.value,
            priority=ItemPriority.P2.value,
            item_type=ItemType.FEATURE.value,
            created_at=now,
            updated_at=now,
            tags=["test", "backend"],
            assigned_to="daedalus"
        )
        assert item.id == "item-abc"
        assert item.title == "Test Item"
        assert item.tags == ["test", "backend"]
        assert item.assigned_to == "daedalus"

    def test_work_item_to_dict(self):
        """to_dict should serialize all fields."""
        now = datetime.now().isoformat()
        item = WorkItem(
            id="item-123",
            title="Test",
            description="Desc",
            status="backlog",
            priority="P2",
            item_type="feature",
            created_at=now,
            updated_at=now,
            project_id="proj-456"
        )
        d = item.to_dict()
        assert d["id"] == "item-123"
        assert d["project_id"] == "proj-456"
        assert "links" in d

    def test_work_item_from_dict(self):
        """from_dict should deserialize correctly."""
        now = datetime.now().isoformat()
        data = {
            "id": "item-xyz",
            "title": "From Dict",
            "description": "Test desc",
            "status": "ready",
            "priority": "P1",
            "item_type": "bug",
            "created_at": now,
            "updated_at": now,
            "tags": ["urgent"],
            "assigned_to": "cass",
            "created_by": "daedalus"
        }
        item = WorkItem.from_dict(data)
        assert item.id == "item-xyz"
        assert item.status == "ready"
        assert item.priority == "P1"
        assert item.created_by == "daedalus"

    def test_work_item_defaults(self):
        """from_dict should use defaults for missing fields."""
        data = {
            "id": "item-min",
            "title": "Minimal",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        item = WorkItem.from_dict(data)
        assert item.status == ItemStatus.BACKLOG.value
        assert item.priority == ItemPriority.P2.value
        assert item.item_type == ItemType.FEATURE.value
        assert item.tags == []
        assert item.links == []

    def test_get_dependencies(self):
        """get_dependencies should return depends_on targets."""
        item = WorkItem(
            id="item-1",
            title="Test",
            description="",
            status="backlog",
            priority="P2",
            item_type="feature",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            links=[
                {"link_type": "depends_on", "target_id": "dep-1"},
                {"link_type": "depends_on", "target_id": "dep-2"},
                {"link_type": "related", "target_id": "rel-1"}
            ]
        )
        deps = item.get_dependencies()
        assert deps == ["dep-1", "dep-2"]

    def test_get_blockers(self):
        """get_blockers should return blocks targets."""
        item = WorkItem(
            id="item-1",
            title="Test",
            description="",
            status="backlog",
            priority="P2",
            item_type="feature",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            links=[
                {"link_type": "blocks", "target_id": "blocked-1"},
                {"link_type": "related", "target_id": "rel-1"}
            ]
        )
        blockers = item.get_blockers()
        assert blockers == ["blocked-1"]

    def test_urgency_score_priority(self):
        """Higher priority should give higher urgency."""
        now = datetime.now().isoformat()

        high = WorkItem(
            id="h", title="High", description="", status="backlog",
            priority="P0", item_type="feature", created_at=now, updated_at=now
        )
        low = WorkItem(
            id="l", title="Low", description="", status="backlog",
            priority="P3", item_type="feature", created_at=now, updated_at=now
        )

        assert high.urgency_score() > low.urgency_score()

    def test_urgency_score_status(self):
        """In-progress status should boost urgency."""
        now = datetime.now().isoformat()

        in_progress = WorkItem(
            id="ip", title="In Progress", description="", status="in_progress",
            priority="P2", item_type="feature", created_at=now, updated_at=now
        )
        backlog = WorkItem(
            id="bl", title="Backlog", description="", status="backlog",
            priority="P2", item_type="feature", created_at=now, updated_at=now
        )

        assert in_progress.urgency_score() > backlog.urgency_score()


# ---------------------------------------------------------------------------
# Milestone Tests
# ---------------------------------------------------------------------------

class TestMilestone:
    """Tests for Milestone dataclass."""

    def test_milestone_creation(self):
        """Should create Milestone with fields."""
        now = datetime.now().isoformat()
        milestone = Milestone(
            id="ms-123",
            title="v1.0 Release",
            description="Initial release",
            target_date="2025-02-01",
            status="active",
            created_at=now,
            updated_at=now
        )
        assert milestone.id == "ms-123"
        assert milestone.title == "v1.0 Release"
        assert milestone.status == "active"

    def test_milestone_to_dict(self):
        """to_dict should serialize all fields."""
        now = datetime.now().isoformat()
        milestone = Milestone(
            id="ms-1", title="Test", description="Desc",
            target_date="2025-01-15", status="active",
            created_at=now, updated_at=now, plan_path="/path/to/plan.md"
        )
        d = milestone.to_dict()
        assert d["id"] == "ms-1"
        assert d["plan_path"] == "/path/to/plan.md"

    def test_milestone_from_dict(self):
        """from_dict should deserialize correctly."""
        now = datetime.now().isoformat()
        data = {
            "id": "ms-xyz",
            "title": "From Dict",
            "description": "Test",
            "target_date": "2025-03-01",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "plan_path": "/plans/xyz.md"
        }
        milestone = Milestone.from_dict(data)
        assert milestone.id == "ms-xyz"
        assert milestone.status == "completed"
        assert milestone.plan_path == "/plans/xyz.md"


# ---------------------------------------------------------------------------
# RoadmapManager Tests
# ---------------------------------------------------------------------------

class TestRoadmapManager:
    """Tests for RoadmapManager."""

    def test_create_item_basic(self, roadmap_manager):
        """create_item should create and persist item."""
        item = roadmap_manager.create_item(
            title="Test Feature",
            description="Implement something"
        )
        assert item.id is not None
        assert len(item.id) == 8  # Short UUID
        assert item.title == "Test Feature"
        assert item.status == ItemStatus.BACKLOG.value
        assert item.priority == ItemPriority.P2.value

    def test_create_item_full(self, roadmap_manager):
        """create_item should accept all parameters."""
        item = roadmap_manager.create_item(
            title="Complex Task",
            description="Detailed description",
            status=ItemStatus.READY.value,
            priority=ItemPriority.P0.value,
            item_type=ItemType.BUG.value,
            tags=["urgent", "backend"],
            assigned_to="daedalus",
            project_id="proj-123",
            created_by="cass"
        )
        assert item.status == ItemStatus.READY.value
        assert item.priority == ItemPriority.P0.value
        assert item.item_type == ItemType.BUG.value
        assert item.tags == ["urgent", "backend"]
        assert item.assigned_to == "daedalus"
        assert item.created_by == "cass"

    def test_load_item(self, roadmap_manager):
        """load_item should retrieve by ID."""
        created = roadmap_manager.create_item(title="Find Me")
        loaded = roadmap_manager.load_item(created.id)
        assert loaded is not None
        assert loaded.title == "Find Me"

    def test_load_item_nonexistent(self, roadmap_manager):
        """load_item should return None for missing ID."""
        result = roadmap_manager.load_item("nonexistent-id")
        assert result is None

    def test_update_item(self, roadmap_manager):
        """update_item should modify fields."""
        item = roadmap_manager.create_item(title="Original", priority=ItemPriority.P3.value)
        updated = roadmap_manager.update_item(
            item.id,
            title="Updated Title",
            priority=ItemPriority.P1.value,
            tags=["new-tag"]
        )
        assert updated.title == "Updated Title"
        assert updated.priority == ItemPriority.P1.value
        assert updated.tags == ["new-tag"]

    def test_update_item_nonexistent(self, roadmap_manager):
        """update_item should return None for missing ID."""
        result = roadmap_manager.update_item("nonexistent", title="New")
        assert result is None

    def test_delete_item(self, roadmap_manager):
        """delete_item should remove item."""
        item = roadmap_manager.create_item(title="Delete Me")
        result = roadmap_manager.delete_item(item.id)
        assert result is True
        assert roadmap_manager.load_item(item.id) is None

    def test_list_items_basic(self, roadmap_manager):
        """list_items should return all non-archived items."""
        roadmap_manager.create_item(title="Item 1")
        roadmap_manager.create_item(title="Item 2")
        roadmap_manager.create_item(title="Item 3", status=ItemStatus.ARCHIVED.value)

        items = roadmap_manager.list_items()
        assert len(items) == 2

    def test_list_items_with_filters(self, roadmap_manager):
        """list_items should filter by status, priority, etc."""
        roadmap_manager.create_item(title="Ready P1", status=ItemStatus.READY.value, priority=ItemPriority.P1.value)
        roadmap_manager.create_item(title="Ready P2", status=ItemStatus.READY.value, priority=ItemPriority.P2.value)
        roadmap_manager.create_item(title="Backlog P1", status=ItemStatus.BACKLOG.value, priority=ItemPriority.P1.value)

        ready_items = roadmap_manager.list_items(status=ItemStatus.READY.value)
        assert len(ready_items) == 2

        p1_items = roadmap_manager.list_items(priority=ItemPriority.P1.value)
        assert len(p1_items) == 2

    def test_list_items_sorted_by_urgency(self, roadmap_manager):
        """list_items should sort by urgency descending."""
        roadmap_manager.create_item(title="Low", priority=ItemPriority.P3.value)
        roadmap_manager.create_item(title="High", priority=ItemPriority.P0.value)
        roadmap_manager.create_item(title="Medium", priority=ItemPriority.P2.value)

        items = roadmap_manager.list_items()
        assert items[0]["title"] == "High"
        assert items[2]["title"] == "Low"

    def test_pick_item(self, roadmap_manager):
        """pick_item should assign and advance status."""
        item = roadmap_manager.create_item(title="Pick Me", status=ItemStatus.READY.value)
        picked = roadmap_manager.pick_item(item.id, "daedalus")

        assert picked.assigned_to == "daedalus"
        assert picked.status == ItemStatus.IN_PROGRESS.value

    def test_complete_item(self, roadmap_manager):
        """complete_item should set status to done."""
        item = roadmap_manager.create_item(title="Complete Me")
        completed = roadmap_manager.complete_item(item.id)

        assert completed.status == ItemStatus.DONE.value

    def test_advance_status(self, roadmap_manager):
        """advance_status should move through workflow."""
        item = roadmap_manager.create_item(title="Advance", status=ItemStatus.BACKLOG.value)

        result = roadmap_manager.advance_status(item.id)
        assert result["item"].status == ItemStatus.READY.value

        result = roadmap_manager.advance_status(item.id)
        assert result["item"].status == ItemStatus.IN_PROGRESS.value


# ---------------------------------------------------------------------------
# Milestone Operations Tests
# ---------------------------------------------------------------------------

class TestMilestoneOperations:
    """Tests for milestone-related operations."""

    def test_create_milestone(self, roadmap_manager):
        """create_milestone should create and persist."""
        milestone = roadmap_manager.create_milestone(
            title="v1.0",
            description="First release",
            target_date="2025-02-01"
        )
        assert milestone.id is not None
        assert milestone.title == "v1.0"
        assert milestone.status == "active"

    def test_list_milestones(self, roadmap_manager):
        """list_milestones should return active milestones."""
        roadmap_manager.create_milestone(title="MS 1")
        roadmap_manager.create_milestone(title="MS 2")

        milestones = roadmap_manager.list_milestones()
        assert len(milestones) == 2

    def test_update_milestone(self, roadmap_manager):
        """update_milestone should modify fields."""
        milestone = roadmap_manager.create_milestone(title="Original")
        updated = roadmap_manager.update_milestone(
            milestone.id,
            title="Updated",
            status="completed"
        )
        assert updated.title == "Updated"
        assert updated.status == "completed"

    def test_get_milestone_progress(self, roadmap_manager):
        """get_milestone_progress should compute stats."""
        milestone = roadmap_manager.create_milestone(title="Progress Test")

        roadmap_manager.create_item(title="Done", milestone_id=milestone.id, status=ItemStatus.DONE.value)
        roadmap_manager.create_item(title="In Progress", milestone_id=milestone.id, status=ItemStatus.IN_PROGRESS.value)
        roadmap_manager.create_item(title="Backlog", milestone_id=milestone.id, status=ItemStatus.BACKLOG.value)

        progress = roadmap_manager.get_milestone_progress(milestone.id)
        assert progress["total_items"] == 3
        assert progress["done_items"] == 1
        assert progress["progress_pct"] == pytest.approx(33.33, rel=0.1)


# ---------------------------------------------------------------------------
# Link Operations Tests
# ---------------------------------------------------------------------------

class TestLinkOperations:
    """Tests for item linking."""

    def test_add_link_basic(self, roadmap_manager):
        """add_link should create link between items."""
        item1 = roadmap_manager.create_item(title="Item 1")
        item2 = roadmap_manager.create_item(title="Item 2")

        result = roadmap_manager.add_link(item1.id, item2.id, LinkType.RELATED.value)

        assert result is not None
        assert len(result.links) == 1
        assert result.links[0]["target_id"] == item2.id

    def test_add_link_bidirectional(self, roadmap_manager):
        """add_link should create inverse for depends_on/blocks."""
        item1 = roadmap_manager.create_item(title="Dependent")
        item2 = roadmap_manager.create_item(title="Dependency")

        roadmap_manager.add_link(item1.id, item2.id, LinkType.DEPENDS_ON.value)

        # Check inverse link was created
        loaded_item2 = roadmap_manager.load_item(item2.id)
        assert any(
            link["link_type"] == LinkType.BLOCKS.value and link["target_id"] == item1.id
            for link in loaded_item2.links
        )

    def test_remove_link(self, roadmap_manager):
        """remove_link should delete link and inverse."""
        item1 = roadmap_manager.create_item(title="Item 1")
        item2 = roadmap_manager.create_item(title="Item 2")

        roadmap_manager.add_link(item1.id, item2.id, LinkType.DEPENDS_ON.value)
        roadmap_manager.remove_link(item1.id, item2.id, LinkType.DEPENDS_ON.value)

        loaded1 = roadmap_manager.load_item(item1.id)
        loaded2 = roadmap_manager.load_item(item2.id)

        assert len(loaded1.links) == 0
        assert len(loaded2.links) == 0

    def test_get_item_links(self, roadmap_manager):
        """get_item_links should resolve targets."""
        item1 = roadmap_manager.create_item(title="Source")
        item2 = roadmap_manager.create_item(title="Target")

        roadmap_manager.add_link(item1.id, item2.id, LinkType.RELATED.value)

        links_info = roadmap_manager.get_item_links(item1.id)
        assert len(links_info["links"]) == 1
        assert links_info["links"][0]["target_title"] == "Target"

    def test_check_dependencies_unmet(self, roadmap_manager):
        """check_dependencies should identify unmet deps."""
        item1 = roadmap_manager.create_item(title="Dependent")
        item2 = roadmap_manager.create_item(title="Dependency", status=ItemStatus.BACKLOG.value)

        roadmap_manager.add_link(item1.id, item2.id, LinkType.DEPENDS_ON.value)

        dep_check = roadmap_manager.check_dependencies(item1.id)
        assert dep_check["has_unmet_dependencies"] is True
        assert len(dep_check["unmet_dependencies"]) == 1

    def test_check_dependencies_met(self, roadmap_manager):
        """check_dependencies should pass when deps are done."""
        item1 = roadmap_manager.create_item(title="Dependent")
        item2 = roadmap_manager.create_item(title="Dependency", status=ItemStatus.DONE.value)

        roadmap_manager.add_link(item1.id, item2.id, LinkType.DEPENDS_ON.value)

        dep_check = roadmap_manager.check_dependencies(item1.id)
        assert dep_check["has_unmet_dependencies"] is False
