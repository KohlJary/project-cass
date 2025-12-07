"""
Wiki Parser - Extract and manipulate wikilinks in markdown content.

Handles Obsidian-style [[wikilinks]] including:
- Simple links: [[PageName]]
- Aliased links: [[PageName|Display Text]]
- Section links: [[PageName#Section]]
"""

import re
from dataclasses import dataclass
from typing import List, Set, Tuple, Optional


# Regex patterns for wikilinks
# Matches [[target]] or [[target|alias]] or [[target#section]] or [[target#section|alias]]
WIKILINK_PATTERN = re.compile(
    r'\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]'
)


@dataclass
class WikiLink:
    """Represents a parsed wikilink."""
    target: str           # The page being linked to
    section: Optional[str] = None  # Optional section within the page
    alias: Optional[str] = None    # Optional display text

    @property
    def display_text(self) -> str:
        """Get the text that should be displayed for this link."""
        if self.alias:
            return self.alias
        if self.section:
            return f"{self.target}#{self.section}"
        return self.target

    def to_markdown(self) -> str:
        """Convert back to markdown wikilink format."""
        result = f"[[{self.target}"
        if self.section:
            result += f"#{self.section}"
        if self.alias:
            result += f"|{self.alias}"
        result += "]]"
        return result

    def __hash__(self):
        return hash((self.target, self.section))

    def __eq__(self, other):
        if not isinstance(other, WikiLink):
            return False
        return self.target == other.target and self.section == other.section


class WikiParser:
    """Parse and manipulate wiki content."""

    @staticmethod
    def extract_links(content: str) -> List[WikiLink]:
        """
        Extract all wikilinks from markdown content.

        Args:
            content: Markdown text containing [[wikilinks]]

        Returns:
            List of WikiLink objects found in the content
        """
        links = []
        for match in WIKILINK_PATTERN.finditer(content):
            target = match.group(1).strip()
            section = match.group(2).strip() if match.group(2) else None
            alias = match.group(3).strip() if match.group(3) else None
            links.append(WikiLink(target=target, section=section, alias=alias))
        return links

    @staticmethod
    def extract_unique_targets(content: str) -> Set[str]:
        """
        Extract unique page targets from wikilinks.

        Args:
            content: Markdown text containing [[wikilinks]]

        Returns:
            Set of unique page names linked to
        """
        links = WikiParser.extract_links(content)
        return {link.target for link in links}

    @staticmethod
    def add_link(content: str, target: str,
                 position: str = "end",
                 section: str = "Related") -> str:
        """
        Add a wikilink to the content.

        Args:
            content: Existing markdown content
            target: Page to link to
            position: Where to add - "end" appends, "related" adds to Related section
            section: Section name to add link under (if position="related")

        Returns:
            Updated content with new link
        """
        link = f"[[{target}]]"

        if position == "end":
            return content.rstrip() + f"\n\n{link}\n"

        # Try to find or create a section for related links
        section_header = f"## {section}"
        if section_header in content:
            # Add to existing section
            lines = content.split('\n')
            result = []
            in_section = False
            added = False

            for i, line in enumerate(lines):
                result.append(line)
                if line.strip() == section_header:
                    in_section = True
                elif in_section and not added:
                    # Add after first blank line or list item in section
                    if line.strip() == "" or line.startswith("- "):
                        if line.strip() == "":
                            result.append(f"- {link}")
                        else:
                            result.append(f"- {link}")
                        added = True
                        in_section = False

            if not added:
                result.append(f"\n- {link}")

            return '\n'.join(result)
        else:
            # Create new section at end
            return content.rstrip() + f"\n\n{section_header}\n\n- {link}\n"

    @staticmethod
    def replace_link(content: str, old_target: str, new_target: str) -> str:
        """
        Replace all links to one page with links to another.

        Args:
            content: Markdown content
            old_target: Current link target to replace
            new_target: New link target

        Returns:
            Content with links updated
        """
        def replacer(match):
            target = match.group(1).strip()
            section = match.group(2)
            alias = match.group(3)

            if target == old_target:
                result = f"[[{new_target}"
                if section:
                    result += f"#{section.strip()}"
                if alias:
                    result += f"|{alias.strip()}"
                result += "]]"
                return result
            return match.group(0)

        return WIKILINK_PATTERN.sub(replacer, content)

    @staticmethod
    def extract_frontmatter(content: str) -> Tuple[dict, str]:
        """
        Extract YAML frontmatter from markdown content.

        Args:
            content: Markdown content potentially starting with ---

        Returns:
            Tuple of (frontmatter dict, remaining content)
        """
        import yaml

        if not content.startswith('---'):
            return {}, content

        # Find the closing ---
        end_match = re.search(r'\n---\s*\n', content[3:])
        if not end_match:
            return {}, content

        frontmatter_str = content[3:end_match.start() + 3]
        remaining = content[end_match.end() + 3:]

        try:
            frontmatter = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError:
            frontmatter = {}

        return frontmatter, remaining.lstrip()

    @staticmethod
    def add_frontmatter(content: str, metadata: dict) -> str:
        """
        Add or update YAML frontmatter in markdown content.

        Args:
            content: Markdown content
            metadata: Dictionary to add as frontmatter

        Returns:
            Content with frontmatter added/updated
        """
        import yaml

        existing_fm, body = WikiParser.extract_frontmatter(content)
        merged = {**existing_fm, **metadata}

        fm_str = yaml.dump(merged, default_flow_style=False, sort_keys=False)
        return f"---\n{fm_str}---\n\n{body}"

    @staticmethod
    def extract_title(content: str) -> Optional[str]:
        """
        Extract the title from markdown content.

        Checks frontmatter 'title' field first, then falls back to
        first H1 heading.

        Args:
            content: Markdown content

        Returns:
            Title string or None
        """
        # Check frontmatter
        frontmatter, body = WikiParser.extract_frontmatter(content)
        if 'title' in frontmatter:
            return frontmatter['title']

        # Look for first H1
        h1_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        if h1_match:
            return h1_match.group(1).strip()

        return None

    @staticmethod
    def extract_sections(content: str) -> List[Tuple[str, str, int]]:
        """
        Extract all sections from markdown content.

        Args:
            content: Markdown content

        Returns:
            List of (heading_text, section_content, level) tuples
        """
        _, body = WikiParser.extract_frontmatter(content)

        sections = []
        current_heading = None
        current_content = []
        current_level = 0

        for line in body.split('\n'):
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                # Save previous section
                if current_heading is not None:
                    sections.append((
                        current_heading,
                        '\n'.join(current_content).strip(),
                        current_level
                    ))

                current_level = len(heading_match.group(1))
                current_heading = heading_match.group(2).strip()
                current_content = []
            else:
                current_content.append(line)

        # Don't forget last section
        if current_heading is not None:
            sections.append((
                current_heading,
                '\n'.join(current_content).strip(),
                current_level
            ))

        return sections
