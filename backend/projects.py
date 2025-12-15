"""
Cass Vessel - Project Manager
Handles project workspaces with working directories and associated files

Storage: SQLite database (data/cass.db)
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path
import uuid

from database import get_db, json_serialize, json_deserialize


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
    # GitHub integration
    github_repo: Optional[str] = None  # e.g., "owner/repo"
    github_token: Optional[str] = None  # Per-project PAT (None = use system default)

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
            "user_id": self.user_id,
            "github_repo": self.github_repo,
            "github_token": self.github_token,
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
            user_id=data.get("user_id"),
            github_repo=data.get("github_repo"),
            github_token=data.get("github_token"),
        )


class ProjectManager:
    """
    Manages project workspaces with SQLite persistence.

    Storage:
        - projects table: Core project metadata
        - project_files table: Files associated with projects
        - project_documents table: Markdown documents within projects
    """

    def __init__(self):
        """
        Initialize ProjectManager.

        Projects are shared across all daemons - no daemon_id filtering.
        """
        pass

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
            documents=[],
            description=description,
            user_id=user_id
        )

        # Save to database
        with get_db() as conn:
            conn.execute("""
                INSERT INTO projects (
                    id, user_id, name, working_directory,
                    description, github_repo, github_token, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                user_id,
                name,
                working_dir,
                description,
                None,
                None,
                now,
                now
            ))

        return project

    def _load_project_files(self, project_id: str) -> List[ProjectFile]:
        """Load project files from database"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT path, description, embedded, added_at
                FROM project_files WHERE project_id = ?
            """, (project_id,))

            files = []
            for row in cursor.fetchall():
                files.append(ProjectFile(
                    path=row['path'],
                    added_at=row['added_at'],
                    description=row['description'],
                    embedded=bool(row['embedded'])
                ))
            return files

    def _load_project_documents(self, project_id: str) -> List[ProjectDocument]:
        """Load project documents from database"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, content, created_at, updated_at, created_by, embedded
                FROM project_documents WHERE project_id = ?
            """, (project_id,))

            docs = []
            for row in cursor.fetchall():
                docs.append(ProjectDocument(
                    id=row['id'],
                    title=row['title'],
                    content=row['content'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    created_by=row['created_by'] or 'cass',
                    embedded=bool(row['embedded'])
                ))
            return docs

    def load_project(self, project_id: str) -> Optional[Project]:
        """Load a project by ID"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, name, working_directory, created_at, updated_at,
                       description, user_id, github_repo, github_token
                FROM projects WHERE id = ?
            """, (project_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Load files and documents
            files = self._load_project_files(project_id)
            documents = self._load_project_documents(project_id)

            return Project(
                id=row['id'],
                name=row['name'],
                working_directory=row['working_directory'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                files=files,
                documents=documents,
                description=row['description'],
                user_id=row['user_id'],
                github_repo=row['github_repo'],
                github_token=row['github_token']
            )

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        working_directory: Optional[str] = None,
        description: Optional[str] = None,
        github_repo: Optional[str] = None,
        github_token: Optional[str] = None,
        clear_github_token: bool = False,
    ) -> Optional[Project]:
        """
        Update project details.

        Args:
            project_id: ID of the project to update
            name: New project name
            working_directory: New working directory
            description: New description
            github_repo: GitHub repo in "owner/repo" format
            github_token: Per-project GitHub PAT (None keeps existing, use clear_github_token to remove)
            clear_github_token: If True, removes the project-specific token (will use system default)
        """
        project = self.load_project(project_id)
        if not project:
            return None

        now = datetime.now().isoformat()

        with get_db() as conn:
            updates = []
            params = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if working_directory is not None:
                updates.append("working_directory = ?")
                params.append(os.path.abspath(os.path.expanduser(working_directory)))
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if github_repo is not None:
                updates.append("github_repo = ?")
                params.append(github_repo if github_repo else None)
            if github_token is not None:
                updates.append("github_token = ?")
                params.append(github_token)
            if clear_github_token:
                updates.append("github_token = ?")
                params.append(None)

            updates.append("updated_at = ?")
            params.append(now)
            params.append(project_id)

            if updates:
                conn.execute(
                    f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
                    params
                )

        return self.load_project(project_id)

    def list_projects(self, user_id: Optional[str] = None) -> List[Dict]:
        """
        List projects with metadata.
        Returns most recently updated first.

        Args:
            user_id: If provided, only return projects for this user
        """
        with get_db() as conn:
            if user_id:
                cursor = conn.execute("""
                    SELECT p.id, p.name, p.working_directory, p.created_at, p.updated_at,
                           p.description, p.user_id, p.github_repo,
                           (SELECT COUNT(*) FROM project_files WHERE project_id = p.id) as file_count
                    FROM projects p
                    WHERE p.user_id = ?
                    ORDER BY p.updated_at DESC
                """, (user_id,))
            else:
                cursor = conn.execute("""
                    SELECT p.id, p.name, p.working_directory, p.created_at, p.updated_at,
                           p.description, p.user_id, p.github_repo,
                           (SELECT COUNT(*) FROM project_files WHERE project_id = p.id) as file_count
                    FROM projects p
                    ORDER BY p.updated_at DESC
                """)

            return [
                {
                    "id": row['id'],
                    "name": row['name'],
                    "working_directory": row['working_directory'],
                    "created_at": row['created_at'],
                    "updated_at": row['updated_at'],
                    "description": row['description'],
                    "user_id": row['user_id'],
                    "github_repo": row['github_repo'],
                    "file_count": row['file_count']
                }
                for row in cursor.fetchall()
            ]

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and its associated files/documents"""
        with get_db() as conn:
            # Delete files and documents first (foreign key constraint)
            conn.execute("DELETE FROM project_files WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM project_documents WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
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

        now = datetime.now().isoformat()

        # Check if already added
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM project_files WHERE project_id = ? AND path = ?",
                (project_id, abs_path)
            )
            if cursor.fetchone():
                # Already exists, return existing file
                for f in project.files:
                    if f.path == abs_path:
                        return f
                return ProjectFile(path=abs_path, added_at=now, description=description)

            # Add file
            conn.execute("""
                INSERT INTO project_files (project_id, path, description, embedded, added_at)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, abs_path, description, 0, now))

            # Update project timestamp
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id)
            )

        return ProjectFile(
            path=abs_path,
            added_at=now,
            description=description,
            embedded=False
        )

    def remove_file(self, project_id: str, file_path: str) -> bool:
        """Remove a file from a project"""
        project = self.load_project(project_id)
        if not project:
            return False

        # Normalize and validate path
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        abs_path = validate_path_within_directory(abs_path, project.working_directory)

        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute(
                "DELETE FROM project_files WHERE project_id = ? AND path = ?",
                (project_id, abs_path)
            )
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id)
            )

        return True

    def mark_file_embedded(self, project_id: str, file_path: str) -> bool:
        """Mark a file as having been embedded"""
        project = self.load_project(project_id)
        if not project:
            return False

        # Normalize and validate path
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        abs_path = validate_path_within_directory(abs_path, project.working_directory)

        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute(
                "UPDATE project_files SET embedded = 1 WHERE project_id = ? AND path = ?",
                (project_id, abs_path)
            )
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id)
            )

        return True

    def get_files(self, project_id: str) -> List[ProjectFile]:
        """Get all files for a project"""
        return self._load_project_files(project_id)

    def get_unembedded_files(self, project_id: str) -> List[ProjectFile]:
        """Get files that haven't been embedded yet"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT path, description, embedded, added_at
                FROM project_files WHERE project_id = ? AND embedded = 0
            """, (project_id,))

            return [
                ProjectFile(
                    path=row['path'],
                    added_at=row['added_at'],
                    description=row['description'],
                    embedded=bool(row['embedded'])
                )
                for row in cursor.fetchall()
            ]

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
        # Verify project exists
        project = self.load_project(project_id)
        if not project:
            return None

        now = datetime.now().isoformat()
        doc_id = str(uuid.uuid4())

        with get_db() as conn:
            conn.execute("""
                INSERT INTO project_documents (
                    id, project_id, title, content, created_by, embedded, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, project_id, title, content, created_by, 0, now, now))

            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id)
            )

        return ProjectDocument(
            id=doc_id,
            title=title,
            content=content,
            created_at=now,
            updated_at=now,
            created_by=created_by,
            embedded=False
        )

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
        now = datetime.now().isoformat()

        with get_db() as conn:
            updates = []
            params = []

            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if content is not None:
                updates.append("content = ?")
                params.append(content)
                updates.append("embedded = 0")  # Mark for re-embedding

            updates.append("updated_at = ?")
            params.append(now)
            params.append(document_id)
            params.append(project_id)

            if updates:
                conn.execute(
                    f"UPDATE project_documents SET {', '.join(updates)} WHERE id = ? AND project_id = ?",
                    params
                )
                conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now, project_id)
                )

        return self.get_document(project_id, document_id)

    def get_document(
        self,
        project_id: str,
        document_id: str
    ) -> Optional[ProjectDocument]:
        """Get a specific document by ID"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, content, created_at, updated_at, created_by, embedded
                FROM project_documents WHERE id = ? AND project_id = ?
            """, (document_id, project_id))
            row = cursor.fetchone()

            if not row:
                return None

            return ProjectDocument(
                id=row['id'],
                title=row['title'],
                content=row['content'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                created_by=row['created_by'] or 'cass',
                embedded=bool(row['embedded'])
            )

    def get_document_by_title(
        self,
        project_id: str,
        title: str
    ) -> Optional[ProjectDocument]:
        """Get a document by title (case-insensitive)"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, content, created_at, updated_at, created_by, embedded
                FROM project_documents WHERE project_id = ? AND LOWER(title) = LOWER(?)
            """, (project_id, title))
            row = cursor.fetchone()

            if not row:
                return None

            return ProjectDocument(
                id=row['id'],
                title=row['title'],
                content=row['content'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                created_by=row['created_by'] or 'cass',
                embedded=bool(row['embedded'])
            )

    def list_documents(self, project_id: str) -> List[ProjectDocument]:
        """Get all documents for a project"""
        return self._load_project_documents(project_id)

    def delete_document(self, project_id: str, document_id: str) -> bool:
        """Delete a document from a project"""
        now = datetime.now().isoformat()

        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM project_documents WHERE id = ? AND project_id = ?",
                (document_id, project_id)
            )
            if cursor.rowcount > 0:
                conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now, project_id)
                )
                return True
        return False

    def mark_document_embedded(self, project_id: str, document_id: str) -> bool:
        """Mark a document as having been embedded"""
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute(
                "UPDATE project_documents SET embedded = 1 WHERE id = ? AND project_id = ?",
                (document_id, project_id)
            )
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id)
            )
        return True

    def get_unembedded_documents(self, project_id: str) -> List[ProjectDocument]:
        """Get documents that haven't been embedded yet"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, title, content, created_at, updated_at, created_by, embedded
                FROM project_documents WHERE project_id = ? AND embedded = 0
            """, (project_id,))

            return [
                ProjectDocument(
                    id=row['id'],
                    title=row['title'],
                    content=row['content'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    created_by=row['created_by'] or 'cass',
                    embedded=bool(row['embedded'])
                )
                for row in cursor.fetchall()
            ]


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
