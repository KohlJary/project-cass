"""
Wiki Storage - File-based storage for wiki pages with git versioning.

Handles:
- CRUD operations for wiki pages (markdown files)
- Git-backed versioning for change history
- Link graph management
- Directory structure for page types
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

from .parser import WikiParser, WikiLink

# Find git executable - needed for systemd services that have limited PATH
GIT_PATH = shutil.which("git") or "/usr/bin/git"


class PageType(Enum):
    """Types of wiki pages based on the spec."""
    ENTITY = "entity"      # People, places, AI systems
    CONCEPT = "concept"    # Ideas, principles, patterns
    RELATIONSHIP = "relationship"  # Connections between entities
    JOURNAL = "journal"    # Temporal reflections
    META = "meta"          # Wiki structure, indices


@dataclass
class WikiPage:
    """Represents a wiki page with content and metadata."""

    name: str  # Page name (used for [[wikilinks]])
    content: str  # Full markdown content including frontmatter
    page_type: PageType = PageType.CONCEPT
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None

    # Cached parsed data
    _frontmatter: Optional[dict] = field(default=None, repr=False)
    _links: Optional[List[WikiLink]] = field(default=None, repr=False)

    @property
    def frontmatter(self) -> dict:
        """Get parsed frontmatter, caching result."""
        if self._frontmatter is None:
            self._frontmatter, _ = WikiParser.extract_frontmatter(self.content)
        return self._frontmatter

    @property
    def links(self) -> List[WikiLink]:
        """Get parsed links, caching result."""
        if self._links is None:
            self._links = WikiParser.extract_links(self.content)
        return self._links

    @property
    def title(self) -> str:
        """Get page title from frontmatter or H1, fallback to name."""
        title = WikiParser.extract_title(self.content)
        return title if title else self.name

    @property
    def body(self) -> str:
        """Get content without frontmatter."""
        _, body = WikiParser.extract_frontmatter(self.content)
        return body

    @property
    def link_targets(self) -> Set[str]:
        """Get unique page names this page links to."""
        return {link.target for link in self.links}

    def invalidate_cache(self) -> None:
        """Clear cached parsed data after content change."""
        self._frontmatter = None
        self._links = None


class WikiStorage:
    """
    File-based wiki storage with git versioning.

    Structure:
        wiki_root/
            entity/
                Kohl.md
                Cass.md
            concept/
                Temple-Codex.md
                Four_Vows.md
            relationship/
                Kohl-Cass.md
            journal/
                2025-01-15.md
            meta/
                Index.md
    """

    def __init__(self, wiki_root: str, git_enabled: bool = True):
        """
        Initialize wiki storage.

        Args:
            wiki_root: Root directory for wiki files
            git_enabled: Whether to use git for versioning
        """
        self.wiki_root = Path(wiki_root)
        self.git_enabled = git_enabled

        # Ensure directory structure exists
        self._ensure_directories()

        # Initialize git if enabled and not already a repo
        if self.git_enabled:
            self._init_git()

    def _ensure_directories(self) -> None:
        """Create directory structure for page types."""
        for page_type in PageType:
            type_dir = self.wiki_root / page_type.value
            type_dir.mkdir(parents=True, exist_ok=True)

    def _init_git(self) -> None:
        """Initialize git repository if not exists."""
        git_dir = self.wiki_root / ".git"
        if not git_dir.exists():
            subprocess.run(
                [GIT_PATH, "init"],
                cwd=self.wiki_root,
                capture_output=True,
                check=True
            )
            # Create initial .gitignore
            gitignore = self.wiki_root / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text("# Wiki-as-Self Memory\n*.swp\n*.tmp\n")
                self._git_commit("Initialize wiki repository")

    def _git_add(self, file_path: Path) -> None:
        """Stage a file for commit."""
        if not self.git_enabled:
            return
        subprocess.run(
            [GIT_PATH, "add", str(file_path.relative_to(self.wiki_root))],
            cwd=self.wiki_root,
            capture_output=True
        )

    def _git_commit(self, message: str) -> None:
        """Create a git commit with the given message."""
        if not self.git_enabled:
            return
        # Check if there are staged changes
        result = subprocess.run(
            [GIT_PATH, "diff", "--cached", "--quiet"],
            cwd=self.wiki_root,
            capture_output=True
        )
        if result.returncode != 0:  # There are staged changes
            subprocess.run(
                [GIT_PATH, "commit", "-m", message,
                 "--author=Cass <cass@vessel.local>"],
                cwd=self.wiki_root,
                capture_output=True
            )

    def _git_rm(self, file_path: Path) -> None:
        """Remove a file from git tracking."""
        if not self.git_enabled:
            return
        subprocess.run(
            [GIT_PATH, "rm", "-f", str(file_path.relative_to(self.wiki_root))],
            cwd=self.wiki_root,
            capture_output=True
        )

    def _name_to_filename(self, name: str) -> str:
        """Convert page name to safe filename."""
        # Replace spaces with underscores, remove problematic chars
        safe = re.sub(r'[<>:"/\\|?*]', '', name)
        safe = safe.replace(' ', '_')
        return f"{safe}.md"

    def _filename_to_name(self, filename: str) -> str:
        """Convert filename back to page name."""
        name = filename.replace('.md', '')
        name = name.replace('_', ' ')
        return name

    def _get_page_path(self, name: str, page_type: PageType) -> Path:
        """Get the file path for a page."""
        filename = self._name_to_filename(name)
        return self.wiki_root / page_type.value / filename

    def create(
        self,
        name: str,
        content: str,
        page_type: PageType = PageType.CONCEPT,
        commit: bool = True
    ) -> WikiPage:
        """
        Create a new wiki page.

        Args:
            name: Page name (for [[wikilinks]])
            content: Markdown content (may include frontmatter)
            page_type: Type of page
            commit: Whether to commit the change

        Returns:
            Created WikiPage

        Raises:
            FileExistsError: If page already exists
        """
        file_path = self._get_page_path(name, page_type)

        if file_path.exists():
            raise FileExistsError(f"Page '{name}' already exists")

        # Ensure frontmatter includes page type and timestamps
        now = datetime.now()
        metadata = {
            "type": page_type.value,
            "created": now.isoformat(),
            "modified": now.isoformat(),
        }

        # Add to existing frontmatter or create new
        existing_fm, body = WikiParser.extract_frontmatter(content)
        merged = {**metadata, **existing_fm}  # User metadata takes precedence
        final_content = WikiParser.add_frontmatter(body, merged)

        # Write file
        file_path.write_text(final_content, encoding='utf-8')

        # Git operations
        if commit:
            self._git_add(file_path)
            self._git_commit(f"Create {page_type.value}: {name}")

        return WikiPage(
            name=name,
            content=final_content,
            page_type=page_type,
            created_at=now,
            modified_at=now
        )

    def read(self, name: str, page_type: Optional[PageType] = None) -> Optional[WikiPage]:
        """
        Read a wiki page by name.

        Args:
            name: Page name
            page_type: Optional type hint (searches all types if None)

        Returns:
            WikiPage if found, None otherwise
        """
        if page_type:
            file_path = self._get_page_path(name, page_type)
            if file_path.exists():
                return self._load_page(file_path, page_type)
            return None

        # Search all page types
        for pt in PageType:
            file_path = self._get_page_path(name, pt)
            if file_path.exists():
                return self._load_page(file_path, pt)

        return None

    def _load_page(self, file_path: Path, page_type: PageType) -> WikiPage:
        """Load a page from file."""
        content = file_path.read_text(encoding='utf-8')
        name = self._filename_to_name(file_path.name)

        # Get timestamps from file stats
        stat = file_path.stat()
        created_at = datetime.fromtimestamp(stat.st_ctime)
        modified_at = datetime.fromtimestamp(stat.st_mtime)

        # Override with frontmatter if present
        fm, _ = WikiParser.extract_frontmatter(content)
        if 'created' in fm:
            try:
                created_at = datetime.fromisoformat(fm['created'])
            except (ValueError, TypeError):
                pass
        if 'modified' in fm:
            try:
                modified_at = datetime.fromisoformat(fm['modified'])
            except (ValueError, TypeError):
                pass

        return WikiPage(
            name=name,
            content=content,
            page_type=page_type,
            created_at=created_at,
            modified_at=modified_at
        )

    def update(
        self,
        name: str,
        content: str,
        page_type: Optional[PageType] = None,
        commit: bool = True
    ) -> Optional[WikiPage]:
        """
        Update an existing wiki page.

        Args:
            name: Page name
            content: New markdown content
            page_type: Type hint (finds automatically if None)
            commit: Whether to commit the change

        Returns:
            Updated WikiPage if found, None if page doesn't exist
        """
        # Find existing page
        existing = self.read(name, page_type)
        if not existing:
            return None

        file_path = self._get_page_path(name, existing.page_type)
        now = datetime.now()

        # Preserve created timestamp, update modified
        fm, body = WikiParser.extract_frontmatter(content)
        fm['modified'] = now.isoformat()
        if 'created' not in fm and existing.created_at:
            fm['created'] = existing.created_at.isoformat()
        fm['type'] = existing.page_type.value

        final_content = WikiParser.add_frontmatter(body, fm)

        # Write file
        file_path.write_text(final_content, encoding='utf-8')

        # Git operations
        if commit:
            self._git_add(file_path)
            self._git_commit(f"Update {existing.page_type.value}: {name}")

        return WikiPage(
            name=name,
            content=final_content,
            page_type=existing.page_type,
            created_at=existing.created_at,
            modified_at=now
        )

    def delete(self, name: str, page_type: Optional[PageType] = None, commit: bool = True) -> bool:
        """
        Delete a wiki page.

        Args:
            name: Page name
            page_type: Type hint (finds automatically if None)
            commit: Whether to commit the change

        Returns:
            True if deleted, False if not found
        """
        existing = self.read(name, page_type)
        if not existing:
            return False

        file_path = self._get_page_path(name, existing.page_type)

        if commit and self.git_enabled:
            self._git_rm(file_path)
            self._git_commit(f"Delete {existing.page_type.value}: {name}")
        else:
            file_path.unlink()

        return True

    def list_pages(self, page_type: Optional[PageType] = None) -> List[WikiPage]:
        """
        List all wiki pages, optionally filtered by type.

        Args:
            page_type: Optional type filter

        Returns:
            List of WikiPage objects
        """
        pages = []
        types = [page_type] if page_type else list(PageType)

        for pt in types:
            type_dir = self.wiki_root / pt.value
            if type_dir.exists():
                for file_path in type_dir.glob("*.md"):
                    pages.append(self._load_page(file_path, pt))

        return pages

    def search(self, query: str, page_type: Optional[PageType] = None) -> List[WikiPage]:
        """
        Search pages by content.

        Args:
            query: Search string (case-insensitive)
            page_type: Optional type filter

        Returns:
            List of matching WikiPage objects
        """
        query_lower = query.lower()
        results = []

        for page in self.list_pages(page_type):
            if query_lower in page.content.lower() or query_lower in page.name.lower():
                results.append(page)

        return results

    def get_backlinks(self, name: str) -> List[WikiPage]:
        """
        Find all pages that link to the given page.

        Args:
            name: Page name to find backlinks for

        Returns:
            List of pages that link to this page
        """
        backlinks = []

        for page in self.list_pages():
            if name in page.link_targets:
                backlinks.append(page)

        return backlinks

    def get_link_graph(self) -> Dict[str, Set[str]]:
        """
        Build the complete link graph of the wiki.

        Returns:
            Dict mapping page name to set of linked page names
        """
        graph = {}

        for page in self.list_pages():
            graph[page.name] = page.link_targets

        return graph

    def find_orphans(self) -> List[WikiPage]:
        """
        Find pages with no incoming links.

        Returns:
            List of orphaned pages (not linked from anywhere)
        """
        all_pages = {page.name: page for page in self.list_pages()}
        linked_pages = set()

        for page in all_pages.values():
            linked_pages.update(page.link_targets)

        orphans = []
        for name, page in all_pages.items():
            # Meta pages (like Index) are okay to be orphans
            if name not in linked_pages and page.page_type != PageType.META:
                orphans.append(page)

        return orphans

    def find_broken_links(self) -> List[Tuple[WikiPage, str]]:
        """
        Find links pointing to non-existent pages.

        Returns:
            List of (source_page, broken_link_target) tuples
        """
        all_page_names = {page.name for page in self.list_pages()}
        broken = []

        for page in self.list_pages():
            for target in page.link_targets:
                if target not in all_page_names:
                    broken.append((page, target))

        return broken

    def get_page_history(self, name: str, page_type: Optional[PageType] = None) -> List[dict]:
        """
        Get git history for a page.

        Args:
            name: Page name
            page_type: Type hint

        Returns:
            List of commit dicts with 'hash', 'date', 'message'
        """
        if not self.git_enabled:
            return []

        existing = self.read(name, page_type)
        if not existing:
            return []

        file_path = self._get_page_path(name, existing.page_type)
        rel_path = file_path.relative_to(self.wiki_root)

        result = subprocess.run(
            [GIT_PATH, "log", "--pretty=format:%H|%aI|%s", "--", str(rel_path)],
            cwd=self.wiki_root,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return []

        history = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('|', 2)
                if len(parts) == 3:
                    history.append({
                        'hash': parts[0],
                        'date': parts[1],
                        'message': parts[2]
                    })

        return history
