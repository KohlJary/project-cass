"""
Cass Vessel - Project Manager
Handles project workspaces with working directories and associated files
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path
import uuid


class PathTraversalError(Exception):
    """Raised when a file path attempts to escape the project directory"""
    pass


def validate_path_within_directory(file_path: str, base_directory: str) -> str:
    """
    Validate that a file path is within a base directory.
    Returns the resolved absolute path if valid.
    Raises PathTraversalError if the path would escape the base directory.
    """
    # Resolve both paths to absolute, normalized form
    base = Path(base_directory).resolve()
    target = Path(file_path).resolve()

    # Check if target is within base (or is base itself)
    try:
        target.relative_to(base)
        return str(target)
    except ValueError:
        raise PathTraversalError(
            f"Path '{file_path}' is outside the project directory '{base_directory}'"
        )


@dataclass
class ProjectFile:
    """A file associated with a project"""
    path: str  # Absolute path to file
    added_at: str
    description: Optional[str] = None
    embedded: bool = False  # Whether it's been chunked and embedded


@dataclass
class ProjectDocument:
    """A markdown document stored within a project (created by Cass or user)"""
    id: str
    title: str
    content: str  # Markdown content
    created_at: str
    updated_at: str
    created_by: str = "cass"  # "cass" or "user"
    embedded: bool = False


@dataclass
class Project:
    """A project workspace"""
    id: str
    name: str
    working_directory: str
    created_at: str
    updated_at: str
    files: List[ProjectFile] = field(default_factory=list)
    documents: List[ProjectDocument] = field(default_factory=list)
    description: Optional[str] = None
    user_id: Optional[str] = None  # Owner of this project

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "working_directory": self.working_directory,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": [asdict(f) for f in self.files],
            "documents": [asdict(d) for d in self.documents],
            "description": self.description,
            "user_id": self.user_id
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Project':
        """Create from dictionary"""
        files = [ProjectFile(**f) for f in data.get("files", [])]
        documents = [ProjectDocument(**d) for d in data.get("documents", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            working_directory=data["working_directory"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            files=files,
            documents=documents,
            description=data.get("description"),
            user_id=data.get("user_id")
        )


class ProjectManager:
    """
    Manages project workspaces with persistence.

    Each project is stored as a separate JSON file.
    Metadata index tracks all projects for listing.
    """

    def __init__(self, storage_dir: str = "./data/projects"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._ensure_index()

    def _ensure_index(self):
        """Ensure index file exists"""
        if not self.index_file.exists():
            self._save_index([])

    def _load_index(self) -> List[Dict]:
        """Load project index"""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_index(self, index: List[Dict]):
        """Save project index"""
        with open(self.index_file, 'w') as f:
            json.dump(index, f, indent=2)

    def _get_project_path(self, project_id: str) -> Path:
        """Get file path for a project"""
        return self.storage_dir / f"{project_id}.json"

    def create_project(
        self,
        name: str,
        working_directory: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Project:
        """Create a new project"""
        project_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # Normalize and validate working directory
        working_dir = os.path.abspath(os.path.expanduser(working_directory))

        project = Project(
            id=project_id,
            name=name,
            working_directory=working_dir,
            created_at=now,
            updated_at=now,
            files=[],
            description=description,
            user_id=user_id
        )

        # Save project
        self._save_project(project)

        # Update index
        index = self._load_index()
        index.append({
            "id": project_id,
            "name": name,
            "working_directory": working_dir,
            "created_at": now,
            "updated_at": now,
            "file_count": 0,
            "user_id": user_id
        })
        self._save_index(index)

        return project

    def _save_project(self, project: Project):
        """Save a project to disk"""
        path = self._get_project_path(project.id)
        with open(path, 'w') as f:
            json.dump(project.to_dict(), f, indent=2)

    def load_project(self, project_id: str) -> Optional[Project]:
        """Load a project by ID"""
        path = self._get_project_path(project_id)

        if not path.exists():
            return None

        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return Project.from_dict(data)
        except (json.JSONDecodeError, FileNotFoundError):
            return None

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        working_directory: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[Project]:
        """Update project details"""
        project = self.load_project(project_id)

        if not project:
            return None

        if name is not None:
            project.name = name
        if working_directory is not None:
            project.working_directory = os.path.abspath(
                os.path.expanduser(working_directory)
            )
        if description is not None:
            project.description = description

        project.updated_at = datetime.now().isoformat()

        self._save_project(project)
        self._update_index_entry(project)

        return project

    def _update_index_entry(self, project: Project):
        """Update a project's entry in the index"""
        index = self._load_index()

        for entry in index:
            if entry["id"] == project.id:
                entry["name"] = project.name
                entry["working_directory"] = project.working_directory
                entry["updated_at"] = project.updated_at
                entry["file_count"] = len(project.files)
                break

        self._save_index(index)

    def list_projects(self, user_id: Optional[str] = None) -> List[Dict]:
        """
        List projects with metadata.
        Returns most recently updated first.

        Args:
            user_id: If provided, only return projects for this user
        """
        index = self._load_index()

        # Filter by user_id if provided
        if user_id:
            index = [p for p in index if p.get("user_id") == user_id]

        # Sort by updated_at descending
        index.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return index

    def delete_project(self, project_id: str) -> bool:
        """Delete a project"""
        path = self._get_project_path(project_id)

        # Delete file
        if path.exists():
            path.unlink()

        # Remove from index
        index = self._load_index()
        index = [entry for entry in index if entry["id"] != project_id]
        self._save_index(index)

        return True

    def add_file(
        self,
        project_id: str,
        file_path: str,
        description: Optional[str] = None
    ) -> Optional[ProjectFile]:
        """Add a file to a project"""
        project = self.load_project(project_id)

        if not project:
            return None

        # Normalize and expand the path
        abs_path = os.path.abspath(os.path.expanduser(file_path))

        # Validate path is within project working directory
        abs_path = validate_path_within_directory(abs_path, project.working_directory)

        # Check if file exists
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"File not found: {abs_path}")

        # Check if already added
        for f in project.files:
            if f.path == abs_path:
                return f  # Already exists

        # Add file
        project_file = ProjectFile(
            path=abs_path,
            added_at=datetime.now().isoformat(),
            description=description,
            embedded=False
        )
        project.files.append(project_file)
        project.updated_at = datetime.now().isoformat()

        self._save_project(project)
        self._update_index_entry(project)

        return project_file

    def remove_file(self, project_id: str, file_path: str) -> bool:
        """Remove a file from a project"""
        project = self.load_project(project_id)

        if not project:
            return False

        # Normalize and validate path
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        abs_path = validate_path_within_directory(abs_path, project.working_directory)

        # Find and remove
        project.files = [f for f in project.files if f.path != abs_path]
        project.updated_at = datetime.now().isoformat()

        self._save_project(project)
        self._update_index_entry(project)

        return True

    def mark_file_embedded(self, project_id: str, file_path: str) -> bool:
        """Mark a file as having been embedded"""
        project = self.load_project(project_id)

        if not project:
            return False

        # Normalize and validate path
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        abs_path = validate_path_within_directory(abs_path, project.working_directory)

        for f in project.files:
            if f.path == abs_path:
                f.embedded = True
                break

        project.updated_at = datetime.now().isoformat()
        self._save_project(project)

        return True

    def get_files(self, project_id: str) -> List[ProjectFile]:
        """Get all files for a project"""
        project = self.load_project(project_id)
        return project.files if project else []

    def get_unembedded_files(self, project_id: str) -> List[ProjectFile]:
        """Get files that haven't been embedded yet"""
        project = self.load_project(project_id)
        if not project:
            return []
        return [f for f in project.files if not f.embedded]

    # === Document Management ===

    def add_document(
        self,
        project_id: str,
        title: str,
        content: str,
        created_by: str = "cass"
    ) -> Optional[ProjectDocument]:
        """
        Add a markdown document to a project.

        Args:
            project_id: ID of the project
            title: Document title
            content: Markdown content
            created_by: "cass" or "user"

        Returns:
            The created ProjectDocument, or None if project not found
        """
        project = self.load_project(project_id)
        if not project:
            return None

        now = datetime.now().isoformat()
        doc_id = str(uuid.uuid4())

        document = ProjectDocument(
            id=doc_id,
            title=title,
            content=content,
            created_at=now,
            updated_at=now,
            created_by=created_by,
            embedded=False
        )

        project.documents.append(document)
        project.updated_at = now
        self._save_project(project)
        self._update_index_entry(project)

        return document

    def update_document(
        self,
        project_id: str,
        document_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None
    ) -> Optional[ProjectDocument]:
        """
        Update a document in a project.

        Args:
            project_id: ID of the project
            document_id: ID of the document
            title: New title (optional)
            content: New content (optional)

        Returns:
            The updated ProjectDocument, or None if not found
        """
        project = self.load_project(project_id)
        if not project:
            return None

        for doc in project.documents:
            if doc.id == document_id:
                if title is not None:
                    doc.title = title
                if content is not None:
                    doc.content = content
                    doc.embedded = False  # Mark for re-embedding
                doc.updated_at = datetime.now().isoformat()

                project.updated_at = doc.updated_at
                self._save_project(project)
                return doc

        return None

    def get_document(
        self,
        project_id: str,
        document_id: str
    ) -> Optional[ProjectDocument]:
        """Get a specific document by ID"""
        project = self.load_project(project_id)
        if not project:
            return None

        for doc in project.documents:
            if doc.id == document_id:
                return doc

        return None

    def get_document_by_title(
        self,
        project_id: str,
        title: str
    ) -> Optional[ProjectDocument]:
        """Get a document by title (case-insensitive)"""
        project = self.load_project(project_id)
        if not project:
            return None

        title_lower = title.lower()
        for doc in project.documents:
            if doc.title.lower() == title_lower:
                return doc

        return None

    def list_documents(self, project_id: str) -> List[ProjectDocument]:
        """Get all documents for a project"""
        project = self.load_project(project_id)
        return project.documents if project else []

    def delete_document(self, project_id: str, document_id: str) -> bool:
        """Delete a document from a project"""
        project = self.load_project(project_id)
        if not project:
            return False

        original_count = len(project.documents)
        project.documents = [d for d in project.documents if d.id != document_id]

        if len(project.documents) < original_count:
            project.updated_at = datetime.now().isoformat()
            self._save_project(project)
            self._update_index_entry(project)
            return True

        return False

    def mark_document_embedded(self, project_id: str, document_id: str) -> bool:
        """Mark a document as having been embedded"""
        project = self.load_project(project_id)
        if not project:
            return False

        for doc in project.documents:
            if doc.id == document_id:
                doc.embedded = True
                break

        project.updated_at = datetime.now().isoformat()
        self._save_project(project)

        return True

    def get_unembedded_documents(self, project_id: str) -> List[ProjectDocument]:
        """Get documents that haven't been embedded yet"""
        project = self.load_project(project_id)
        if not project:
            return []
        return [d for d in project.documents if not d.embedded]


if __name__ == "__main__":
    # Test the project manager
    manager = ProjectManager("./data/projects_test")

    # Create project
    project = manager.create_project(
        name="Test Project",
        working_directory="~/code/test",
        description="A test project"
    )
    print(f"Created project: {project.id}")

    # Add a file
    try:
        manager.add_file(project.id, __file__, "This test file")
        print("Added file")
    except FileNotFoundError as e:
        print(f"File error: {e}")

    # List projects
    projects = manager.list_projects()
    print(f"\nProjects: {len(projects)}")
    for p in projects:
        print(f"  - {p['name']} ({p['file_count']} files)")

    # Load and display
    loaded = manager.load_project(project.id)
    print(f"\nLoaded project: {loaded.name}")
    print(f"  Working dir: {loaded.working_directory}")
    print(f"  Files: {len(loaded.files)}")
