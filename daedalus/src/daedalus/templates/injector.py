"""
Template injection for Daedalus CLAUDE.md files.

Handles injecting and updating the managed Daedalus section in project
CLAUDE.md files. Uses importlib.resources to load template from package data.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Python 3.9+ has importlib.resources.files, 3.7-3.8 need importlib_resources
if sys.version_info >= (3, 9):
    from importlib.resources import files
else:
    from importlib_resources import files

# Markers for the managed section
DAEDALUS_BEGIN = "<!-- DAEDALUS_BEGIN -->"
DAEDALUS_END = "<!-- DAEDALUS_END -->"

# Default config location (can be overridden)
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "daedalus" / "config.json"


def _debug_log(msg: str, level: str = "info") -> None:
    """Simple debug logging - integrates with calling code's logger if available."""
    # Can be replaced with proper logging in the future
    pass


def get_template_content() -> Optional[str]:
    """
    Load the CLAUDE_TEMPLATE.md from package data.

    Returns:
        Template content string, or None if not found.
    """
    try:
        template_files = files("daedalus.templates") / "data" / "CLAUDE_TEMPLATE.md"
        return template_files.read_text()
    except Exception as e:
        _debug_log(f"Failed to load template from package: {e}", "warning")
        return None


def load_daedalus_config(config_path: Optional[Path] = None) -> dict:
    """
    Load Daedalus configuration from config file.

    Args:
        config_path: Path to config file. Defaults to ~/.config/daedalus/config.json
                     or falls back to project config/daedalus.json

    Returns:
        Configuration dictionary.
    """
    paths_to_try = []

    if config_path:
        paths_to_try.append(config_path)

    # Try default config locations
    paths_to_try.extend([
        DEFAULT_CONFIG_PATH,
        Path.cwd() / "config" / "daedalus.json",  # Project-local config
    ])

    for path in paths_to_try:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception as e:
                _debug_log(f"Failed to load config from {path}: {e}", "warning")

    return {}


def substitute_template_vars(content: str, config: dict) -> str:
    """
    Substitute template variables with config values.

    Args:
        content: Template content with {{VAR}} placeholders.
        config: Configuration dictionary with user settings.

    Returns:
        Content with variables substituted.
    """
    user_config = config.get("user", {})

    replacements = {
        "{{USER_NAME}}": user_config.get("name", "the user"),
        "{{USER_COMMUNICATION_STYLE}}": user_config.get("communication_style", "Not specified"),
    }

    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    return content


def inject_claude_template(
    working_dir: str,
    config_path: Optional[Path] = None,
    template_content: Optional[str] = None,
) -> bool:
    """
    Inject or update the Daedalus section in a project's CLAUDE.md.

    If CLAUDE.md doesn't exist, creates it from the template.
    If it exists but has no Daedalus section, prepends the section.
    If it exists with a Daedalus section, updates that section only.

    Template variables (e.g., {{USER_NAME}}) are substituted from config.

    Args:
        working_dir: Path to project working directory.
        config_path: Optional path to config file.
        template_content: Optional template content (for testing or override).

    Returns:
        True if injection succeeded, False otherwise.
    """
    if not working_dir or not os.path.isdir(working_dir):
        return False

    claude_md_path = Path(working_dir) / "CLAUDE.md"

    # Get template content
    if template_content is None:
        template_content = get_template_content()

    if not template_content:
        _debug_log("Could not load template content", "warning")
        return False

    # Load config and substitute variables
    config = load_daedalus_config(config_path)
    template_content = substitute_template_vars(template_content, config)

    # Extract just the Daedalus section from template
    match = re.search(
        rf'{re.escape(DAEDALUS_BEGIN)}.*?{re.escape(DAEDALUS_END)}',
        template_content,
        re.DOTALL
    )
    if not match:
        _debug_log("Could not find Daedalus markers in template", "warning")
        return False

    daedalus_section = match.group(0)

    try:
        if not claude_md_path.exists():
            # Create new file from template
            claude_md_path.write_text(template_content)
            _debug_log(f"Created CLAUDE.md at {claude_md_path}", "info")
        else:
            # Update existing file
            existing_content = claude_md_path.read_text()

            if DAEDALUS_BEGIN in existing_content:
                # Replace existing Daedalus section
                updated_content = re.sub(
                    rf'{re.escape(DAEDALUS_BEGIN)}.*?{re.escape(DAEDALUS_END)}',
                    daedalus_section,
                    existing_content,
                    flags=re.DOTALL
                )
                claude_md_path.write_text(updated_content)
                _debug_log(f"Updated Daedalus section in {claude_md_path}", "info")
            else:
                # Prepend Daedalus section to existing content
                updated_content = daedalus_section + "\n\n" + existing_content
                claude_md_path.write_text(updated_content)
                _debug_log(f"Prepended Daedalus section to {claude_md_path}", "info")

        return True

    except Exception as e:
        _debug_log(f"Error injecting template: {e}", "error")
        return False
