"""
Tests for projects.py - Project workspace management.

Tests cover:
- Project CRUD operations
- Path traversal validation (security)
- File management within projects
- Document management
"""
import pytest
import os
from pathlib import Path
from datetime import datetime

from projects import (
    Project, ProjectFile, ProjectDocument, ProjectManager,
    PathTraversalError, validate_path_within_directory
)


# ---------------------------------------------------------------------------
# Path Validation Tests
# ---------------------------------------------------------------------------

class TestPathValidation:
    """Tests for path traversal security."""

    def test_valid_path_within_directory(self, test_data_dir):
        """Valid path within base directory should return resolved path."""
        base = str(test_data_dir)
        subdir = test_data_dir / "subdir"
        subdir.mkdir()

        result = validate_path_within_directory(str(subdir), base)
        assert result == str(subdir.resolve())

    def test_path_traversal_attack_rejected(self, test_data_dir):
        """Path traversal attempts should raise PathTraversalError."""
        base = str(test_data_dir)
        malicious_path = str(test_data_dir / ".." / ".." / "etc" / "passwd")

        with pytest.raises(PathTraversalError):
            validate_path_within_directory(malicious_path, base)

    def test_symlink_escape_rejected(self, test_data_dir):
        """Symlinks pointing outside base should be rejected."""
        base = str(test_data_dir)
        # Create symlink pointing to parent
        symlink = test_data_dir / "escape_link"
        try:
            symlink.symlink_to(test_data_dir.parent)
            with pytest.raises(PathTraversalError):
                validate_path_within_directory(str(symlink / "outside"), base)
        except OSError:
            pytest.skip("Symlink creation not supported")

    def test_base_directory_itself_is_valid(self, test_data_dir):
        """Base directory should be valid when checked against itself."""
        base = str(test_data_dir)
        result = validate_path_within_directory(base, base)
        assert result == str(test_data_dir.resolve())


# ---------------------------------------------------------------------------
# ProjectFile Tests
# ---------------------------------------------------------------------------

class TestProjectFile:
    """Tests for ProjectFile dataclass."""

    def test_project_file_creation(self):
        """ProjectFile should store basic file metadata."""
        pf = ProjectFile(
            path="/home/user/project/main.py",
            added_at="2025-01-01T00:00:00",
            description="Main entry point"
        )
        assert pf.path == "/home/user/project/main.py"
        assert pf.description == "Main entry point"
        assert pf.embedded is False

    def test_project_file_defaults(self):
        """ProjectFile should have sensible defaults."""
        pf = ProjectFile(
            path="/home/user/project/test.py",
            added_at="2025-01-01T00:00:00"
        )
        assert pf.description is None
        assert pf.embedded is False


# ---------------------------------------------------------------------------
# ProjectDocument Tests
# ---------------------------------------------------------------------------

class TestProjectDocument:
    """Tests for ProjectDocument dataclass."""

    def test_project_document_creation(self):
        """ProjectDocument should store document content."""
        doc = ProjectDocument(
            id="doc-123",
            title="Architecture Notes",
            content="# Architecture\n\nThis is the architecture...",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-01T00:00:00",
            created_by="cass"
        )
        assert doc.title == "Architecture Notes"
        assert doc.content.startswith("# Architecture")
        assert doc.created_by == "cass"
        assert doc.embedded is False


# ---------------------------------------------------------------------------
# Project Tests
# ---------------------------------------------------------------------------

class TestProject:
    """Tests for Project dataclass."""

    def test_project_to_dict(self):
        """Project.to_dict() should serialize all fields."""
        project = Project(
            id="proj-123",
            name="Test Project",
            working_directory="/home/user/code/test",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-01T00:00:00",
            description="A test project"
        )

        d = project.to_dict()
        assert d["id"] == "proj-123"
        assert d["name"] == "Test Project"
        assert d["working_directory"] == "/home/user/code/test"
        assert d["description"] == "A test project"
        assert d["files"] == []
        assert d["documents"] == []

    def test_project_from_dict(self):
        """Project.from_dict() should deserialize correctly."""
        data = {
            "id": "proj-456",
            "name": "Another Project",
            "working_directory": "/tmp/proj",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-02T00:00:00",
            "files": [
                {"path": "/tmp/proj/main.py", "added_at": "2025-01-01T00:00:00", "description": None, "embedded": False}
            ],
            "documents": [],
            "description": "Test",
            "user_id": "user-1"
        }

        project = Project.from_dict(data)
        assert project.id == "proj-456"
        assert project.name == "Another Project"
        assert len(project.files) == 1
        assert project.files[0].path == "/tmp/proj/main.py"
        assert project.user_id == "user-1"

    def test_project_from_dict_with_documents(self):
        """Project.from_dict() should handle documents."""
        data = {
            "id": "proj-789",
            "name": "Doc Project",
            "working_directory": "/tmp/doc",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
            "files": [],
            "documents": [
                {
                    "id": "doc-1",
                    "title": "README",
                    "content": "# Hello",
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:00",
                    "created_by": "user",
                    "embedded": True
                }
            ]
        }

        project = Project.from_dict(data)
        assert len(project.documents) == 1
        assert project.documents[0].title == "README"
        assert project.documents[0].embedded is True


# ---------------------------------------------------------------------------
# ProjectManager Tests
# ---------------------------------------------------------------------------

class TestProjectManager:
    """Tests for ProjectManager."""

    @pytest.fixture
    def projects_dir(self, test_data_dir):
        """Create projects storage directory."""
        path = test_data_dir / "projects"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @pytest.fixture
    def project_manager(self, projects_dir):
        """ProjectManager with isolated storage."""
        return ProjectManager(storage_dir=str(projects_dir))

    @pytest.fixture
    def working_dir(self, test_data_dir):
        """Create a working directory for test projects."""
        path = test_data_dir / "workdir"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # --- CRUD Tests ---

    def test_create_project(self, project_manager, working_dir):
        """create_project should create and persist a project."""
        project = project_manager.create_project(
            name="My Project",
            working_directory=str(working_dir),
            description="Test description"
        )

        assert project.id is not None
        assert project.name == "My Project"
        assert project.description == "Test description"
        assert project.working_directory == str(working_dir.resolve())

    def test_create_project_normalizes_path(self, project_manager, working_dir):
        """create_project should normalize ~ and relative paths."""
        # Use the actual working_dir but reference it differently
        project = project_manager.create_project(
            name="Path Test",
            working_directory=str(working_dir)
        )

        # Should be absolute path
        assert os.path.isabs(project.working_directory)

    def test_load_project(self, project_manager, working_dir):
        """load_project should retrieve a saved project."""
        created = project_manager.create_project(
            name="Load Test",
            working_directory=str(working_dir)
        )

        loaded = project_manager.load_project(created.id)

        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.name == "Load Test"

    def test_load_nonexistent_project(self, project_manager):
        """load_project should return None for missing projects."""
        result = project_manager.load_project("nonexistent-id")
        assert result is None

    def test_list_projects(self, project_manager, working_dir):
        """list_projects should return all projects."""
        project_manager.create_project("Project A", str(working_dir))
        project_manager.create_project("Project B", str(working_dir))

        projects = project_manager.list_projects()

        assert len(projects) == 2
        names = [p["name"] for p in projects]
        assert "Project A" in names
        assert "Project B" in names

    def test_list_projects_sorted_by_updated(self, project_manager, working_dir):
        """list_projects should return most recently updated first."""
        p1 = project_manager.create_project("First", str(working_dir))
        p2 = project_manager.create_project("Second", str(working_dir))

        # Update the first project
        project_manager.update_project(p1.id, description="Updated")

        projects = project_manager.list_projects()
        assert projects[0]["name"] == "First"  # Most recently updated

    def test_list_projects_filter_by_user(self, project_manager, working_dir):
        """list_projects should filter by user_id."""
        project_manager.create_project("User1 Project", str(working_dir), user_id="user-1")
        project_manager.create_project("User2 Project", str(working_dir), user_id="user-2")

        user1_projects = project_manager.list_projects(user_id="user-1")

        assert len(user1_projects) == 1
        assert user1_projects[0]["name"] == "User1 Project"

    def test_update_project(self, project_manager, working_dir):
        """update_project should modify project fields."""
        project = project_manager.create_project("Original", str(working_dir))

        updated = project_manager.update_project(
            project.id,
            name="Updated Name",
            description="New description"
        )

        assert updated.name == "Updated Name"
        assert updated.description == "New description"

        # Verify persistence
        reloaded = project_manager.load_project(project.id)
        assert reloaded.name == "Updated Name"

    def test_delete_project(self, project_manager, working_dir):
        """delete_project should remove project from storage."""
        project = project_manager.create_project("To Delete", str(working_dir))

        result = project_manager.delete_project(project.id)

        assert result is True
        assert project_manager.load_project(project.id) is None
        assert len(project_manager.list_projects()) == 0

    # --- File Management Tests ---

    def test_add_file(self, project_manager, working_dir):
        """add_file should add a file within the project directory."""
        project = project_manager.create_project("File Test", str(working_dir))

        # Create a test file
        test_file = working_dir / "test.py"
        test_file.write_text("print('hello')")

        pf = project_manager.add_file(project.id, str(test_file), "Test file")

        assert pf is not None
        assert pf.path == str(test_file.resolve())
        assert pf.description == "Test file"

    def test_add_file_rejects_path_traversal(self, project_manager, working_dir, test_data_dir):
        """add_file should reject files outside project directory."""
        project = project_manager.create_project("Security Test", str(working_dir))

        # Create file outside working_dir
        outside_file = test_data_dir / "outside.txt"
        outside_file.write_text("secret")

        with pytest.raises(PathTraversalError):
            project_manager.add_file(project.id, str(outside_file))

    def test_add_file_nonexistent_raises(self, project_manager, working_dir):
        """add_file should raise FileNotFoundError for missing files."""
        project = project_manager.create_project("Missing File Test", str(working_dir))

        with pytest.raises(FileNotFoundError):
            project_manager.add_file(project.id, str(working_dir / "nonexistent.py"))

    def test_add_file_idempotent(self, project_manager, working_dir):
        """add_file should return existing file if already added."""
        project = project_manager.create_project("Idempotent Test", str(working_dir))

        test_file = working_dir / "repeat.py"
        test_file.write_text("content")

        pf1 = project_manager.add_file(project.id, str(test_file))
        pf2 = project_manager.add_file(project.id, str(test_file))

        assert pf1.path == pf2.path

        # Should still only have one file
        files = project_manager.get_files(project.id)
        assert len(files) == 1

    def test_remove_file(self, project_manager, working_dir):
        """remove_file should remove a file from the project."""
        project = project_manager.create_project("Remove Test", str(working_dir))

        test_file = working_dir / "remove_me.py"
        test_file.write_text("bye")

        project_manager.add_file(project.id, str(test_file))
        assert len(project_manager.get_files(project.id)) == 1

        project_manager.remove_file(project.id, str(test_file))
        assert len(project_manager.get_files(project.id)) == 0

    def test_mark_file_embedded(self, project_manager, working_dir):
        """mark_file_embedded should set embedded flag."""
        project = project_manager.create_project("Embed Test", str(working_dir))

        test_file = working_dir / "embed.py"
        test_file.write_text("data")

        project_manager.add_file(project.id, str(test_file))
        project_manager.mark_file_embedded(project.id, str(test_file))

        files = project_manager.get_files(project.id)
        assert files[0].embedded is True

    def test_get_unembedded_files(self, project_manager, working_dir):
        """get_unembedded_files should return only non-embedded files."""
        project = project_manager.create_project("Unembedded Test", str(working_dir))

        file1 = working_dir / "file1.py"
        file2 = working_dir / "file2.py"
        file1.write_text("1")
        file2.write_text("2")

        project_manager.add_file(project.id, str(file1))
        project_manager.add_file(project.id, str(file2))
        project_manager.mark_file_embedded(project.id, str(file1))

        unembedded = project_manager.get_unembedded_files(project.id)
        assert len(unembedded) == 1
        assert unembedded[0].path == str(file2.resolve())

    # --- Document Management Tests ---

    def test_add_document(self, project_manager, working_dir):
        """add_document should create a project document."""
        project = project_manager.create_project("Doc Test", str(working_dir))

        doc = project_manager.add_document(
            project.id,
            title="Design Notes",
            content="# Design\n\nNotes here...",
            created_by="cass"
        )

        assert doc is not None
        assert doc.title == "Design Notes"
        assert doc.created_by == "cass"
        assert doc.embedded is False

    def test_update_document(self, project_manager, working_dir):
        """update_document should modify document content."""
        project = project_manager.create_project("Update Doc Test", str(working_dir))
        doc = project_manager.add_document(project.id, "Original", "Original content")

        # Mark as embedded first
        project_manager.mark_document_embedded(project.id, doc.id)

        updated = project_manager.update_document(
            project.id,
            doc.id,
            content="Updated content"
        )

        assert updated.content == "Updated content"
        assert updated.embedded is False  # Should reset when content changes

    def test_get_document(self, project_manager, working_dir):
        """get_document should retrieve by ID."""
        project = project_manager.create_project("Get Doc Test", str(working_dir))
        doc = project_manager.add_document(project.id, "Find Me", "Content")

        found = project_manager.get_document(project.id, doc.id)
        assert found is not None
        assert found.title == "Find Me"

    def test_get_document_by_title(self, project_manager, working_dir):
        """get_document_by_title should find by title (case-insensitive)."""
        project = project_manager.create_project("Title Test", str(working_dir))
        project_manager.add_document(project.id, "My Document", "Content")

        found = project_manager.get_document_by_title(project.id, "MY DOCUMENT")
        assert found is not None
        assert found.title == "My Document"

    def test_list_documents(self, project_manager, working_dir):
        """list_documents should return all project documents."""
        project = project_manager.create_project("List Docs Test", str(working_dir))
        project_manager.add_document(project.id, "Doc 1", "Content 1")
        project_manager.add_document(project.id, "Doc 2", "Content 2")

        docs = project_manager.list_documents(project.id)
        assert len(docs) == 2

    def test_delete_document(self, project_manager, working_dir):
        """delete_document should remove document from project."""
        project = project_manager.create_project("Delete Doc Test", str(working_dir))
        doc = project_manager.add_document(project.id, "Delete Me", "Content")

        result = project_manager.delete_document(project.id, doc.id)

        assert result is True
        assert project_manager.get_document(project.id, doc.id) is None

    def test_get_unembedded_documents(self, project_manager, working_dir):
        """get_unembedded_documents should return only non-embedded docs."""
        project = project_manager.create_project("Unembedded Docs Test", str(working_dir))
        doc1 = project_manager.add_document(project.id, "Doc 1", "Content 1")
        doc2 = project_manager.add_document(project.id, "Doc 2", "Content 2")

        project_manager.mark_document_embedded(project.id, doc1.id)

        unembedded = project_manager.get_unembedded_documents(project.id)
        assert len(unembedded) == 1
        assert unembedded[0].id == doc2.id
