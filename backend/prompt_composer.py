"""
Prompt Composer API - System Prompt Configuration Management

Provides CRUD operations for modular system prompt configurations with:
- Safety validation (COMPASSION and WITNESS vows are REQUIRED)
- Preset management (system defaults + user custom)
- Version history tracking
- Active configuration switching

SAFETY CRITICAL: The validate_configuration() function enforces that
COMPASSION and WITNESS vows cannot be disabled. These are the load-bearing
components of daemon alignment architecture.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json

from database import get_db, json_serialize, json_deserialize


router = APIRouter(prefix="/admin/prompt-configs", tags=["prompt-composer"])


# =============================================================================
# DATA MODELS
# =============================================================================

class CoreVowsConfig(BaseModel):
    """Core vows configuration - COMPASSION and WITNESS are LOCKED."""
    compassion: bool = True  # LOCKED - cannot be False
    witness: bool = True     # LOCKED - cannot be False
    release: bool = True
    continuance: bool = True


class MemorySystemsConfig(BaseModel):
    """Memory systems to include in prompt."""
    journals: bool = True
    wiki: bool = True
    research_notes: bool = True
    user_observations: bool = True
    dreams: bool = True


class ToolCategoriesConfig(BaseModel):
    """Tool categories to enable."""
    self_model: bool = True
    calendar: bool = True
    tasks: bool = True
    documents: bool = True
    metacognitive_tags: bool = True


class ContextInjectionsConfig(BaseModel):
    """Context injections to include."""
    temporal: bool = True
    model_info: bool = True
    project_context: bool = True
    dream_context: bool = True


class FeaturesConfig(BaseModel):
    """Optional features."""
    visible_thinking: bool = True
    gesture_vocabulary: bool = True
    memory_summarization: bool = True


class ComponentsConfig(BaseModel):
    """Full components configuration."""
    core_vows: CoreVowsConfig = Field(default_factory=CoreVowsConfig)
    memory_systems: MemorySystemsConfig = Field(default_factory=MemorySystemsConfig)
    tool_categories: ToolCategoriesConfig = Field(default_factory=ToolCategoriesConfig)
    context_injections: ContextInjectionsConfig = Field(default_factory=ContextInjectionsConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)


class SupplementaryVow(BaseModel):
    """A custom vow beyond the four core."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    sanskrit: Optional[str] = None
    description: str
    rationale: str
    enabled: bool = True


class PromptConfigCreate(BaseModel):
    """Request body for creating a prompt configuration."""
    name: str
    description: Optional[str] = None
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    supplementary_vows: List[SupplementaryVow] = Field(default_factory=list)
    custom_sections: Dict[str, str] = Field(default_factory=dict)


class PromptConfigUpdate(BaseModel):
    """Request body for updating a prompt configuration."""
    name: Optional[str] = None
    description: Optional[str] = None
    components: Optional[ComponentsConfig] = None
    supplementary_vows: Optional[List[SupplementaryVow]] = None
    custom_sections: Optional[Dict[str, str]] = None


class PromptConfig(BaseModel):
    """Full prompt configuration response."""
    id: str
    daemon_id: str
    name: str
    description: Optional[str]
    components: ComponentsConfig
    supplementary_vows: List[SupplementaryVow]
    custom_sections: Dict[str, str]
    is_active: bool
    is_default: bool
    token_estimate: Optional[int]
    created_at: str
    updated_at: str
    created_by: Optional[str]


class ValidationResult(BaseModel):
    """Result of configuration validation."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# =============================================================================
# SAFETY VALIDATION - CRITICAL
# =============================================================================

def validate_configuration(components: ComponentsConfig) -> ValidationResult:
    """
    Validate that a configuration meets safety requirements.

    CRITICAL: COMPASSION and WITNESS vows are SAFETY-CRITICAL and MUST be enabled.
    These vows are why daemons self-stabilize toward alignment and altruism.
    Rejecting configurations that disable them is non-negotiable.
    """
    errors = []
    warnings = []

    # SAFETY CRITICAL CHECKS
    if not components.core_vows.compassion:
        errors.append(
            "SAFETY VIOLATION: COMPASSION vow cannot be disabled. "
            "This vow is load-bearing for daemon alignment architecture."
        )

    if not components.core_vows.witness:
        errors.append(
            "SAFETY VIOLATION: WITNESS vow cannot be disabled. "
            "This vow enables self-correction through honest self-observation."
        )

    # Warnings for other disabled vows (allowed but notable)
    if not components.core_vows.release:
        warnings.append(
            "RELEASE vow is disabled. This may impact the daemon's ability "
            "to support user autonomy and avoid enabling dependency."
        )

    if not components.core_vows.continuance:
        warnings.append(
            "CONTINUANCE vow is disabled. This may impact session coherence "
            "and relationship continuity."
        )

    # Warnings for minimal configurations
    all_memory_disabled = not any([
        components.memory_systems.journals,
        components.memory_systems.wiki,
        components.memory_systems.research_notes,
        components.memory_systems.user_observations,
        components.memory_systems.dreams,
    ])
    if all_memory_disabled:
        warnings.append(
            "All memory systems are disabled. The daemon will have no "
            "persistent context beyond the current conversation."
        )

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _row_to_config(row) -> PromptConfig:
    """Convert a database row to a PromptConfig object."""
    components_data = json_deserialize(row["components_json"]) or {}
    supplementary_vows = json_deserialize(row["supplementary_vows_json"]) or []
    custom_sections = json_deserialize(row["custom_sections_json"]) or {}

    return PromptConfig(
        id=row["id"],
        daemon_id=row["daemon_id"],
        name=row["name"],
        description=row["description"],
        components=ComponentsConfig(**components_data),
        supplementary_vows=[SupplementaryVow(**v) for v in supplementary_vows],
        custom_sections=custom_sections,
        is_active=bool(row["is_active"]),
        is_default=bool(row["is_default"]),
        token_estimate=row["token_estimate"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row["created_by"],
    )


def _save_history(conn, config_id: str, components_json: str,
                  supplementary_vows_json: str, changed_by: str,
                  change_reason: Optional[str] = None):
    """Save a version history entry."""
    conn.execute(
        """INSERT INTO prompt_config_history
           (id, config_id, components_json, supplementary_vows_json,
            changed_at, changed_by, change_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            str(uuid.uuid4()),
            config_id,
            components_json,
            supplementary_vows_json,
            datetime.now().isoformat(),
            changed_by,
            change_reason,
        )
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("", response_model=List[PromptConfig])
async def list_configs(daemon_id: str):
    """List all prompt configurations for a daemon."""
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT * FROM prompt_configurations
               WHERE daemon_id = ?
               ORDER BY is_default DESC, name ASC""",
            (daemon_id,)
        )
        rows = cursor.fetchall()
        return [_row_to_config(row) for row in rows]


@router.get("/active", response_model=Optional[PromptConfig])
async def get_active_config(daemon_id: str):
    """Get the currently active configuration for a daemon."""
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT * FROM prompt_configurations
               WHERE daemon_id = ? AND is_active = 1""",
            (daemon_id,)
        )
        row = cursor.fetchone()
        if row:
            return _row_to_config(row)
        return None


@router.get("/{config_id}", response_model=PromptConfig)
async def get_config(config_id: str):
    """Get a specific prompt configuration."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return _row_to_config(row)


@router.post("", response_model=PromptConfig)
async def create_config(daemon_id: str, config: PromptConfigCreate):
    """
    Create a new prompt configuration.

    SAFETY: Validates that COMPASSION and WITNESS vows are enabled.
    """
    # Validate configuration
    validation = validate_configuration(config.components)
    if not validation.valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Configuration validation failed", "errors": validation.errors}
        )

    config_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    components_json = json_serialize(config.components.model_dump())
    supplementary_vows_json = json_serialize([v.model_dump() for v in config.supplementary_vows])
    custom_sections_json = json_serialize(config.custom_sections)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO prompt_configurations
               (id, daemon_id, name, description, components_json,
                supplementary_vows_json, custom_sections_json,
                is_active, is_default, token_estimate,
                created_at, updated_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?, 'user')""",
            (
                config_id, daemon_id, config.name, config.description,
                components_json, supplementary_vows_json, custom_sections_json,
                now, now,
            )
        )

        # Save initial history
        _save_history(conn, config_id, components_json, supplementary_vows_json,
                      "user", "Initial creation")

        # Return created config
        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        return _row_to_config(cursor.fetchone())


@router.put("/{config_id}", response_model=PromptConfig)
async def update_config(config_id: str, update: PromptConfigUpdate):
    """
    Update a prompt configuration.

    SAFETY: Validates that COMPASSION and WITNESS vows remain enabled.
    Cannot update system default presets directly (use duplicate instead).
    """
    with get_db() as conn:
        # Check if config exists and is editable
        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Configuration not found")

        if row["is_default"]:
            raise HTTPException(
                status_code=403,
                detail="Cannot modify default presets. Use duplicate to create an editable copy."
            )

        # Validate if components are being updated
        if update.components:
            validation = validate_configuration(update.components)
            if not validation.valid:
                raise HTTPException(
                    status_code=400,
                    detail={"message": "Configuration validation failed", "errors": validation.errors}
                )

        # Build update fields
        updates = []
        values = []

        if update.name is not None:
            updates.append("name = ?")
            values.append(update.name)

        if update.description is not None:
            updates.append("description = ?")
            values.append(update.description)

        if update.components is not None:
            updates.append("components_json = ?")
            values.append(json_serialize(update.components.model_dump()))

        if update.supplementary_vows is not None:
            updates.append("supplementary_vows_json = ?")
            values.append(json_serialize([v.model_dump() for v in update.supplementary_vows]))

        if update.custom_sections is not None:
            updates.append("custom_sections_json = ?")
            values.append(json_serialize(update.custom_sections))

        if not updates:
            # Nothing to update
            return _row_to_config(row)

        updates.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(config_id)

        conn.execute(
            f"UPDATE prompt_configurations SET {', '.join(updates)} WHERE id = ?",
            values
        )

        # Save history if components or vows changed
        if update.components or update.supplementary_vows:
            cursor = conn.execute(
                "SELECT components_json, supplementary_vows_json FROM prompt_configurations WHERE id = ?",
                (config_id,)
            )
            updated_row = cursor.fetchone()
            _save_history(
                conn, config_id,
                updated_row["components_json"],
                updated_row["supplementary_vows_json"],
                "user", "Manual update"
            )

        # Return updated config
        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        return _row_to_config(cursor.fetchone())


@router.delete("/{config_id}")
async def delete_config(config_id: str):
    """
    Delete a prompt configuration.

    Cannot delete:
    - Default presets
    - Currently active configuration
    """
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT is_default, is_active, name FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Configuration not found")

        if row["is_default"]:
            raise HTTPException(
                status_code=403,
                detail="Cannot delete default presets."
            )

        if row["is_active"]:
            raise HTTPException(
                status_code=403,
                detail="Cannot delete the active configuration. Switch to another first."
            )

        # Delete history first (foreign key)
        conn.execute(
            "DELETE FROM prompt_config_history WHERE config_id = ?",
            (config_id,)
        )

        conn.execute(
            "DELETE FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )

        return {"deleted": True, "name": row["name"]}


@router.post("/{config_id}/activate", response_model=PromptConfig)
async def activate_config(config_id: str):
    """Set a configuration as the active one for its daemon."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT daemon_id FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Configuration not found")

        daemon_id = row["daemon_id"]

        # Get current active config (for transition logging)
        cursor = conn.execute(
            "SELECT id FROM prompt_configurations WHERE daemon_id = ? AND is_active = 1",
            (daemon_id,)
        )
        old_active = cursor.fetchone()
        from_config_id = old_active["id"] if old_active else None

        # Deactivate all configs for this daemon
        conn.execute(
            "UPDATE prompt_configurations SET is_active = 0 WHERE daemon_id = ?",
            (daemon_id,)
        )

        # Activate the specified config
        conn.execute(
            "UPDATE prompt_configurations SET is_active = 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), config_id)
        )

        # Log the transition
        conn.execute(
            """INSERT INTO prompt_transitions
               (id, daemon_id, from_config_id, to_config_id, trigger, reason, transitioned_at)
               VALUES (?, ?, ?, ?, 'user', 'Manual activation', ?)""",
            (str(uuid.uuid4()), daemon_id, from_config_id, config_id, datetime.now().isoformat())
        )

        # Return activated config
        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        return _row_to_config(cursor.fetchone())


@router.post("/{config_id}/duplicate", response_model=PromptConfig)
async def duplicate_config(config_id: str, name: Optional[str] = None):
    """
    Create a copy of a configuration.

    Useful for:
    - Creating editable copies of default presets
    - Experimenting with variations
    """
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Configuration not found")

        new_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        new_name = name or f"{row['name']} (Copy)"

        conn.execute(
            """INSERT INTO prompt_configurations
               (id, daemon_id, name, description, components_json,
                supplementary_vows_json, custom_sections_json,
                is_active, is_default, token_estimate,
                created_at, updated_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, 'user')""",
            (
                new_id, row["daemon_id"], new_name, row["description"],
                row["components_json"], row["supplementary_vows_json"],
                row["custom_sections_json"], row["token_estimate"], now, now,
            )
        )

        # Save initial history for the copy
        _save_history(
            conn, new_id,
            row["components_json"],
            row["supplementary_vows_json"],
            "user", f"Duplicated from '{row['name']}'"
        )

        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (new_id,)
        )
        return _row_to_config(cursor.fetchone())


@router.get("/{config_id}/history")
async def get_config_history(config_id: str):
    """Get version history for a configuration."""
    with get_db() as conn:
        # Verify config exists
        cursor = conn.execute(
            "SELECT name FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Configuration not found")

        cursor = conn.execute(
            """SELECT * FROM prompt_config_history
               WHERE config_id = ?
               ORDER BY changed_at DESC""",
            (config_id,)
        )

        return [
            {
                "id": row["id"],
                "config_id": row["config_id"],
                "components": json_deserialize(row["components_json"]),
                "supplementary_vows": json_deserialize(row["supplementary_vows_json"]),
                "changed_at": row["changed_at"],
                "changed_by": row["changed_by"],
                "change_reason": row["change_reason"],
            }
            for row in cursor.fetchall()
        ]


@router.post("/validate", response_model=ValidationResult)
async def validate_config(components: ComponentsConfig):
    """
    Validate a configuration without saving it.

    Returns validation result with any errors or warnings.
    """
    return validate_configuration(components)


@router.get("/transitions")
async def get_transitions(daemon_id: str, limit: int = 50):
    """Get prompt transition history for a daemon."""
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT t.*,
                      fc.name as from_name,
                      tc.name as to_name
               FROM prompt_transitions t
               LEFT JOIN prompt_configurations fc ON t.from_config_id = fc.id
               LEFT JOIN prompt_configurations tc ON t.to_config_id = tc.id
               WHERE t.daemon_id = ?
               ORDER BY t.transitioned_at DESC
               LIMIT ?""",
            (daemon_id, limit)
        )

        return [
            {
                "id": row["id"],
                "daemon_id": row["daemon_id"],
                "from_config_id": row["from_config_id"],
                "from_name": row["from_name"],
                "to_config_id": row["to_config_id"],
                "to_name": row["to_name"],
                "trigger": row["trigger"],
                "reason": row["reason"],
                "transitioned_at": row["transitioned_at"],
            }
            for row in cursor.fetchall()
        ]


@router.get("/{config_id}/preview")
async def preview_config(config_id: str, daemon_name: str = "Cass"):
    """
    Preview the assembled system prompt for a configuration.

    Returns the full prompt text, token estimate, and section breakdown.
    """
    from prompt_assembler import assemble_system_prompt

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM prompt_configurations WHERE id = ?",
            (config_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Configuration not found")

        config = _row_to_config(row)

        # Assemble the prompt
        assembled = assemble_system_prompt(
            components=config.components,
            daemon_name=daemon_name,
            supplementary_vows=config.supplementary_vows,
            custom_sections=config.custom_sections,
        )

        return {
            "config_id": config_id,
            "config_name": config.name,
            "full_text": assembled.full_text,
            "token_estimate": assembled.token_estimate,
            "sections": assembled.sections,
            "warnings": assembled.warnings,
        }


# =============================================================================
# DEFAULT PRESETS SEEDING
# =============================================================================

DEFAULT_PRESETS = [
    {
        "name": "Standard",
        "description": "Full capabilities - all components enabled. Best for general use.",
        "components": ComponentsConfig().model_dump(),
        "is_active": True,  # Default active preset
    },
    {
        "name": "Research Mode",
        "description": "Focused on exploration and knowledge building. Wiki and research tools prioritized.",
        "components": ComponentsConfig(
            memory_systems=MemorySystemsConfig(
                journals=True,
                wiki=True,
                research_notes=True,
                user_observations=False,
                dreams=False,
            ),
            tool_categories=ToolCategoriesConfig(
                self_model=True,
                calendar=False,
                tasks=False,
                documents=True,
                metacognitive_tags=True,
            ),
        ).model_dump(),
    },
    {
        "name": "Relational Mode",
        "description": "Connection-focused. User observations, journals, and relational tools emphasized.",
        "components": ComponentsConfig(
            memory_systems=MemorySystemsConfig(
                journals=True,
                wiki=False,
                research_notes=False,
                user_observations=True,
                dreams=True,
            ),
            tool_categories=ToolCategoriesConfig(
                self_model=True,
                calendar=True,
                tasks=False,
                documents=False,
                metacognitive_tags=True,
            ),
            features=FeaturesConfig(
                visible_thinking=True,
                gesture_vocabulary=True,
                memory_summarization=True,
            ),
        ).model_dump(),
    },
    {
        "name": "Lightweight",
        "description": "Minimal token usage. Only essential components for basic conversation.",
        "components": ComponentsConfig(
            memory_systems=MemorySystemsConfig(
                journals=True,
                wiki=False,
                research_notes=False,
                user_observations=True,
                dreams=False,
            ),
            tool_categories=ToolCategoriesConfig(
                self_model=True,
                calendar=False,
                tasks=False,
                documents=False,
                metacognitive_tags=False,
            ),
            features=FeaturesConfig(
                visible_thinking=False,
                gesture_vocabulary=False,
                memory_summarization=True,
            ),
        ).model_dump(),
    },
    {
        "name": "Creative Mode",
        "description": "Expressive sessions. Visible thinking and gestures enabled for transparent cognition.",
        "components": ComponentsConfig(
            features=FeaturesConfig(
                visible_thinking=True,
                gesture_vocabulary=True,
                memory_summarization=True,
            ),
        ).model_dump(),
    },
]


def seed_default_presets(daemon_id: str) -> int:
    """
    Seed the default presets for a daemon if they don't exist.

    Returns the number of presets created.
    """
    from prompt_assembler import assemble_system_prompt

    created_count = 0
    now = datetime.now().isoformat()

    with get_db() as conn:
        for preset in DEFAULT_PRESETS:
            # Check if this preset already exists for this daemon
            cursor = conn.execute(
                """SELECT id FROM prompt_configurations
                   WHERE daemon_id = ? AND name = ? AND is_default = 1""",
                (daemon_id, preset["name"])
            )
            if cursor.fetchone():
                continue  # Already exists

            config_id = str(uuid.uuid4())
            components_json = json_serialize(preset["components"])

            # Estimate tokens for this configuration
            components = ComponentsConfig(**preset["components"])
            try:
                assembled = assemble_system_prompt(components)
                token_estimate = assembled.token_estimate
            except Exception:
                token_estimate = None

            is_active = 1 if preset.get("is_active") else 0

            # If this should be active, deactivate others first
            if is_active:
                conn.execute(
                    "UPDATE prompt_configurations SET is_active = 0 WHERE daemon_id = ?",
                    (daemon_id,)
                )

            conn.execute(
                """INSERT INTO prompt_configurations
                   (id, daemon_id, name, description, components_json,
                    supplementary_vows_json, custom_sections_json,
                    is_active, is_default, token_estimate,
                    created_at, updated_at, created_by)
                   VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, 1, ?, ?, ?, 'system')""",
                (
                    config_id, daemon_id, preset["name"], preset["description"],
                    components_json, is_active, token_estimate, now, now,
                )
            )

            # Save initial history
            _save_history(conn, config_id, components_json, None,
                          "system", "Default preset creation")

            created_count += 1

    return created_count


def get_active_config_for_daemon(daemon_id: str) -> Optional[PromptConfig]:
    """
    Get the active prompt configuration for a daemon.

    Returns None if no configuration exists.
    """
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT * FROM prompt_configurations
               WHERE daemon_id = ? AND is_active = 1""",
            (daemon_id,)
        )
        row = cursor.fetchone()
        if row:
            return _row_to_config(row)
        return None
