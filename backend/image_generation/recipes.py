"""
Recipe System

Save and load successful generation parameter combinations.
Recipes allow Cass to remember and reuse settings that worked well.
"""

import json
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from .generation_params import GenerationParams

logger = logging.getLogger(__name__)


@dataclass
class Recipe:
    """
    A saved generation parameter combination.

    Recipes capture successful generation settings so they can be
    reused for similar creative goals.
    """
    id: str
    name: str
    description: str
    daemon_id: str

    # The saved parameters
    params: GenerationParams

    # Metadata
    created_from_image_id: Optional[str] = None  # "This worked well for image X"
    tags: list[str] = field(default_factory=list)  # e.g., ["portrait", "moody"]
    use_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "daemon_id": self.daemon_id,
            "params": self.params.to_dict(),
            "created_from_image_id": self.created_from_image_id,
            "tags": self.tags,
            "use_count": self.use_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            daemon_id=data["daemon_id"],
            params=GenerationParams.from_dict(data["params"]),
            created_from_image_id=data.get("created_from_image_id"),
            tags=data.get("tags", []),
            use_count=data.get("use_count", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class RecipeManager:
    """
    Manages saved generation recipes.

    Recipes are stored in the database (generation_recipes table) and
    provide a way to save and reuse successful generation settings.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the recipe manager.

        Args:
            db_path: Path to SQLite database. If None, uses default.
        """
        self._db_path = db_path
        self._conn = None

    def _get_connection(self):
        """Get database connection (lazy initialization)."""
        if self._conn is None:
            import sqlite3
            if self._db_path is None:
                # Import from main database module
                from ..database import get_connection
                return get_connection()
            self._conn = sqlite3.connect(self._db_path)
        return self._conn

    def save_recipe(
        self,
        name: str,
        daemon_id: str,
        params: GenerationParams,
        description: str = "",
        from_image_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Recipe:
        """
        Save a new recipe.

        Args:
            name: Display name for the recipe
            daemon_id: ID of the daemon owning this recipe
            params: Generation parameters to save
            description: Description of what this recipe is good for
            from_image_id: Image ID that inspired this recipe
            tags: Search/filter tags

        Returns:
            The created Recipe
        """
        import uuid

        recipe_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        recipe = Recipe(
            id=recipe_id,
            name=name,
            description=description,
            daemon_id=daemon_id,
            params=params,
            created_from_image_id=from_image_id,
            tags=tags or [],
            use_count=0,
            created_at=now,
            updated_at=now,
        )

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO generation_recipes
            (id, daemon_id, name, description, params_json, source_image_id, tags_json, use_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recipe.id,
                recipe.daemon_id,
                recipe.name,
                recipe.description,
                json.dumps(recipe.params.to_dict()),
                recipe.created_from_image_id,
                json.dumps(recipe.tags),
                recipe.use_count,
                recipe.created_at,
                recipe.updated_at,
            ),
        )
        conn.commit()

        logger.info(f"Saved recipe '{name}' (id={recipe_id}) for daemon {daemon_id}")
        return recipe

    def load_recipe(self, name: str, daemon_id: str) -> Optional[Recipe]:
        """
        Load a recipe by name.

        Args:
            name: Recipe name
            daemon_id: Daemon ID (recipes are per-daemon)

        Returns:
            Recipe if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, daemon_id, name, description, params_json, source_image_id,
                   tags_json, use_count, created_at, updated_at
            FROM generation_recipes
            WHERE name = ? AND daemon_id = ?
            """,
            (name, daemon_id),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_recipe(row)

    def get_recipe(self, recipe_id: str) -> Optional[Recipe]:
        """Load a recipe by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, daemon_id, name, description, params_json, source_image_id,
                   tags_json, use_count, created_at, updated_at
            FROM generation_recipes
            WHERE id = ?
            """,
            (recipe_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_recipe(row)

    def list_recipes(
        self,
        daemon_id: str,
        tags: Optional[list[str]] = None,
        limit: int = 50,
    ) -> list[Recipe]:
        """
        List recipes for a daemon.

        Args:
            daemon_id: Daemon ID
            tags: Filter by tags (any match)
            limit: Maximum results

        Returns:
            List of recipes
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, daemon_id, name, description, params_json, source_image_id,
                   tags_json, use_count, created_at, updated_at
            FROM generation_recipes
            WHERE daemon_id = ?
            ORDER BY use_count DESC, updated_at DESC
            LIMIT ?
        """

        cursor.execute(query, (daemon_id, limit))
        rows = cursor.fetchall()

        recipes = [self._row_to_recipe(row) for row in rows]

        # Filter by tags if specified
        if tags:
            tag_set = set(t.lower() for t in tags)
            recipes = [
                r for r in recipes
                if any(t.lower() in tag_set for t in r.tags)
            ]

        return recipes

    def increment_use_count(self, recipe_id: str) -> bool:
        """
        Increment the use count for a recipe.

        Called when a recipe is used for generation.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE generation_recipes
            SET use_count = use_count + 1, updated_at = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(), recipe_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def delete_recipe(self, recipe_id: str) -> bool:
        """Delete a recipe."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM generation_recipes WHERE id = ?", (recipe_id,))
        conn.commit()
        return cursor.rowcount > 0

    def update_recipe(
        self,
        recipe_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        params: Optional[GenerationParams] = None,
        tags: Optional[list[str]] = None,
    ) -> Optional[Recipe]:
        """Update a recipe's fields."""
        recipe = self.get_recipe(recipe_id)
        if not recipe:
            return None

        conn = self._get_connection()
        cursor = conn.cursor()

        updates = ["updated_at = ?"]
        values = [datetime.now().isoformat()]

        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if params is not None:
            updates.append("params_json = ?")
            values.append(json.dumps(params.to_dict()))
        if tags is not None:
            updates.append("tags_json = ?")
            values.append(json.dumps(tags))

        values.append(recipe_id)

        cursor.execute(
            f"UPDATE generation_recipes SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        conn.commit()

        return self.get_recipe(recipe_id)

    def _row_to_recipe(self, row: tuple) -> Recipe:
        """Convert a database row to a Recipe object."""
        return Recipe(
            id=row[0],
            daemon_id=row[1],
            name=row[2],
            description=row[3] or "",
            params=GenerationParams.from_dict(json.loads(row[4])),
            created_from_image_id=row[5],
            tags=json.loads(row[6]) if row[6] else [],
            use_count=row[7] or 0,
            created_at=row[8] or "",
            updated_at=row[9] or "",
        )


# Singleton instance
_manager: Optional[RecipeManager] = None


def get_recipe_manager() -> RecipeManager:
    """Get the singleton recipe manager instance."""
    global _manager
    if _manager is None:
        _manager = RecipeManager()
    return _manager
