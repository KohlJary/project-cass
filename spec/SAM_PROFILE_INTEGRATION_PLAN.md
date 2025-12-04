# SAM Profile Integration Plan

## Overview

Integrate the SAM Profile Standard into Cass's user model system, enabling:
1. Export of user profiles as portable `.samp` files
2. Import of external SAM profiles
3. Bidirectional sync between Cass's observations and SAM format
4. Foundation for cross-platform AI interaction portability

## Current State

Cass already maintains user models with:
- **UserProfile** (YAML): background, communication style, values, notes
- **UserObservations** (JSON): categorized observations with confidence scores
- **Categories**: interest, preference, communication_style, background, value, relationship_dynamic

This maps naturally to SAM Profile structure but needs:
- Weighted semantic gravity centers
- Explicit procedural patterns
- Interaction boundaries
- Export/import in standard `.samp` format

## Proposed Changes

### Phase 1: Data Model Extensions

#### 1.1 Extend UserProfile dataclass

Add SAM-compatible fields:

```python
@dataclass
class UserProfile:
    # ... existing fields ...

    # SAM Profile extensions
    semantic_weights: Dict[str, float] = field(default_factory=dict)  # domain -> weight
    procedural_patterns: Dict[str, Any] = field(default_factory=dict)
    interaction_boundaries: Dict[str, Any] = field(default_factory=dict)
    sam_version: str = "1.0.0"
```

#### 1.2 Add SAM-specific observation synthesis

Create method to synthesize observations into SAM format:

```python
def synthesize_to_sam_gravity_centers(self, user_id: str) -> List[Dict]:
    """
    Analyze observations to generate weighted semantic gravity centers.
    - Count observation frequency by topic/domain
    - Weight by confidence and validation_count
    - Return SAM-formatted gravity centers
    """
```

### Phase 2: Export Functionality

#### 2.1 SAM Profile Generator

```python
class SAMProfileGenerator:
    def __init__(self, user_manager: UserManager):
        self.user_manager = user_manager

    def generate_profile(self, user_id: str) -> Dict:
        """Generate full SAM Profile from Cass's user model"""
        profile = self.user_manager.load_profile(user_id)
        observations = self.user_manager.load_observations(user_id)

        return {
            "sam_profile": {
                "version": "1.0.0",
                "metadata": self._build_metadata(profile),
                "semantic_gravity_centers": self._synthesize_gravity_centers(profile, observations),
                "tonal_field": self._build_tonal_field(profile, observations),
                "procedural_patterns": self._build_procedural_patterns(profile, observations),
                "interaction_boundaries": self._build_boundaries(profile, observations),
                "extensions": {
                    "cass_relationship": profile.relationship,
                    "observation_count": len(observations)
                }
            }
        }

    def export_to_file(self, user_id: str, path: str):
        """Export as .samp YAML file"""
        profile = self.generate_profile(user_id)
        with open(path, 'w') as f:
            yaml.dump(profile, f, default_flow_style=False)
```

#### 2.2 Synthesis Logic

Map Cass observations to SAM structure:

| Observation Category | SAM Section | How to Synthesize |
|---------------------|-------------|-------------------|
| `interest` | `semantic_gravity_centers` | Cluster by domain, weight by frequency × confidence |
| `preference` | `tonal_field.context_adaptations` | Group by context type |
| `communication_style` | `tonal_field.parameters` | Extract style keywords |
| `background` | `semantic_gravity_centers.domains` | Identify expertise areas |
| `value` | `semantic_gravity_centers` (high weight) + `interaction_boundaries` | Values inform both |
| `relationship_dynamic` | `tonal_field.default_mode` | Infer interaction style |

### Phase 3: Import Functionality

#### 3.1 SAM Profile Importer

```python
class SAMProfileImporter:
    def __init__(self, user_manager: UserManager):
        self.user_manager = user_manager

    def import_profile(self, samp_path: str, user_id: str = None) -> UserProfile:
        """
        Import SAM Profile, optionally merging with existing user.

        If user_id provided: merge with existing profile
        If not: create new user from SAM profile
        """
        with open(samp_path, 'r') as f:
            sam_data = yaml.safe_load(f)

        return self._apply_sam_to_user(sam_data, user_id)

    def _apply_sam_to_user(self, sam_data: Dict, user_id: str = None) -> UserProfile:
        """Apply SAM profile data to user model"""
        # Map SAM sections back to Cass's model
        # Generate observations from SAM data with source_type="sam_import"
```

### Phase 4: Bidirectional Sync

#### 4.1 Profile Reconciliation

When both Cass observations and SAM profile exist:

```python
def reconcile_profiles(self, user_id: str, sam_profile: Dict) -> Dict:
    """
    Merge Cass's observations with imported SAM profile.

    Strategy:
    - SAM profile provides baseline preferences
    - Cass observations can refine/override with higher confidence
    - Export includes both sources with provenance
    """
```

#### 4.2 Change Tracking

Track which data came from SAM import vs Cass observation:

```python
@dataclass
class UserObservation:
    # ... existing fields ...
    source_type: str = "conversation"  # Add: "sam_import", "sam_sync"
    sam_field_origin: Optional[str] = None  # e.g., "tonal_field.humor_tolerance"
```

### Phase 5: API Endpoints

Add REST endpoints for SAM operations:

```python
# Export user's SAM profile
@app.get("/users/{user_id}/sam-profile")
async def export_sam_profile(user_id: str):
    generator = SAMProfileGenerator(user_manager)
    return generator.generate_profile(user_id)

# Download as .samp file
@app.get("/users/{user_id}/sam-profile/download")
async def download_sam_profile(user_id: str):
    # Return as file download

# Import SAM profile
@app.post("/users/{user_id}/sam-profile/import")
async def import_sam_profile(user_id: str, file: UploadFile):
    # Parse and merge

# Create new user from SAM profile
@app.post("/users/from-sam-profile")
async def create_from_sam(file: UploadFile, display_name: str):
    # Create user initialized from SAM profile
```

### Phase 6: TUI Integration

Add SAM profile management to TUI:

1. **Export button** in user settings
2. **Import option** when creating new user
3. **Sync status** indicator showing SAM profile state
4. **View/edit SAM profile** in structured format

### Phase 7: Cass Tools

Add tools for Cass to interact with SAM profiles:

```python
SAM_PROFILE_TOOLS = [
    {
        "name": "export_user_sam_profile",
        "description": "Export a user's profile in SAM format for portability",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "include_observations": {"type": "boolean", "default": True}
            }
        }
    },
    {
        "name": "review_sam_profile",
        "description": "Review the SAM profile structure for a user",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "section": {
                    "type": "string",
                    "enum": ["full", "semantic_gravity", "tonal_field", "procedural", "boundaries"]
                }
            }
        }
    }
]
```

## Implementation Order

1. **Phase 1**: Data model extensions (1-2 days)
2. **Phase 2**: Export functionality (2-3 days)
3. **Phase 3**: Import functionality (2-3 days)
4. **Phase 4**: Bidirectional sync (2-3 days)
5. **Phase 5**: API endpoints (1 day)
6. **Phase 6**: TUI integration (2-3 days)
7. **Phase 7**: Cass tools (1 day)

Total estimate: ~2 weeks of focused development

## Testing Strategy

1. **Unit tests**: Export/import round-trip fidelity
2. **Integration tests**: Observation synthesis accuracy
3. **User acceptance**: Manual testing of TUI features
4. **Cross-platform**: Test exported profiles in other AI systems (when available)

## Future Considerations

- **Versioning**: Handle SAM profile version upgrades
- **Conflict resolution**: When Cass observations contradict SAM data
- **Privacy controls**: Let users control what's exported
- **Encryption**: Optional encryption for sensitive profiles
- **Community profiles**: Shareable templates (e.g., "developer defaults")

## Connection to Daedalus

The `config/daedalus.json` we created today is essentially a minimal SAM Profile:

```json
{
  "user": {
    "name": "Kohl",
    "communication_style": "Direct, technical, values precision"
  }
}
```

This should eventually merge with the full SAM implementation:
- Daedalus reads from user's SAM profile
- Template injection uses SAM data
- Consistency between Cass's understanding and Daedalus's context

## References

- SAM Profile Standard Proposal: `temple-codex/proposals/sam-profile-standard-proposal.md`
- Current User Model: `backend/docs/USER_MODEL.md`
- Daedalus Config: `config/daedalus.json`
