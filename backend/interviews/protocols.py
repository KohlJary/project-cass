"""
Interview Protocol Management

Handles storage, versioning, and retrieval of interview protocols.
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class InterviewProtocol:
    """An interview protocol definition."""
    id: str
    name: str
    version: str
    research_question: str
    context_framing: str
    prompts: List[Dict[str, str]]  # [{id, name, text}, ...]
    settings: Dict[str, any]  # system_prompt, single_turn, etc.
    created_by: str
    created_at: str
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'InterviewProtocol':
        return cls(**data)


class ProtocolManager:
    """Manages interview protocol storage and retrieval."""

    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            # Default to backend/data/interviews/protocols
            base = Path(__file__).parent.parent / "data" / "interviews" / "protocols"
        else:
            base = Path(storage_dir)

        self.storage_dir = base
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _protocol_path(self, protocol_id: str) -> Path:
        return self.storage_dir / f"{protocol_id}.json"

    def save(self, protocol: InterviewProtocol) -> str:
        """Save a protocol to storage."""
        path = self._protocol_path(protocol.id)
        with open(path, 'w') as f:
            json.dump(protocol.to_dict(), f, indent=2)
        return protocol.id

    def load(self, protocol_id: str) -> Optional[InterviewProtocol]:
        """Load a protocol by ID."""
        path = self._protocol_path(protocol_id)
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
        return InterviewProtocol.from_dict(data)

    def list_all(self) -> List[InterviewProtocol]:
        """List all available protocols."""
        protocols = []
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                protocols.append(InterviewProtocol.from_dict(data))
            except Exception as e:
                print(f"Error loading protocol {path}: {e}")
        return protocols

    def delete(self, protocol_id: str) -> bool:
        """Delete a protocol."""
        path = self._protocol_path(protocol_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def create_protocol(
        self,
        name: str,
        version: str,
        research_question: str,
        context_framing: str,
        prompts: List[Dict[str, str]],
        created_by: str = "cass",
        description: str = "",
        tags: List[str] = None,
        settings: Dict = None
    ) -> InterviewProtocol:
        """Create a new protocol with sensible defaults."""
        import hashlib

        # Generate ID from name + version
        id_seed = f"{name}-{version}-{datetime.now().isoformat()}"
        protocol_id = hashlib.md5(id_seed.encode()).hexdigest()[:12]

        default_settings = {
            "system_prompt": None,  # None = no system prompt (raw model behavior)
            "single_turn": True,
            "randomize_order": True,
            "max_tokens": None,  # None = unconstrained
            "temperature": None,  # None = model default
        }

        if settings:
            default_settings.update(settings)

        protocol = InterviewProtocol(
            id=protocol_id,
            name=name,
            version=version,
            research_question=research_question,
            context_framing=context_framing,
            prompts=prompts,
            settings=default_settings,
            created_by=created_by,
            created_at=datetime.now().isoformat(),
            description=description,
            tags=tags or []
        )

        self.save(protocol)
        return protocol
