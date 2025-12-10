"""
Interview Response Storage

Handles storage and retrieval of interview responses with provenance tracking.
Also manages annotations on responses.
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class Annotation:
    """An annotation on a response."""
    id: str
    response_id: str
    prompt_id: str
    start_offset: int  # Character offset in response text
    end_offset: int
    highlighted_text: str
    note: str
    annotation_type: str  # observation, question, insight, concern
    created_at: str
    created_by: str = "cass"

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Annotation':
        return cls(**data)


@dataclass
class InterviewResponse:
    """A complete interview response from one model."""
    id: str
    protocol_id: str
    protocol_version: str
    model_name: str
    model_id: str
    provider: str
    timestamp: str
    responses: List[Dict]  # Per-prompt responses
    metadata: Dict
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'InterviewResponse':
        return cls(**data)


class ResponseStorage:
    """Manages interview response storage and retrieval."""

    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            base = Path(__file__).parent.parent / "data" / "interviews"
        else:
            base = Path(storage_dir)

        self.responses_dir = base / "responses"
        self.annotations_dir = base / "annotations"

        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.annotations_dir.mkdir(parents=True, exist_ok=True)

    def _response_path(self, response_id: str) -> Path:
        return self.responses_dir / f"{response_id}.json"

    def _annotations_path(self, response_id: str) -> Path:
        return self.annotations_dir / f"{response_id}_annotations.json"

    def save_response(self, response_data: Dict) -> str:
        """
        Save an interview response.

        Args:
            response_data: Dict from InterviewDispatcher.run_interview()

        Returns:
            Response ID
        """
        response_id = str(uuid.uuid4())[:12]

        interview_response = InterviewResponse(
            id=response_id,
            protocol_id=response_data["protocol_id"],
            protocol_version=response_data["protocol_version"],
            model_name=response_data["model_name"],
            model_id=response_data["model_id"],
            provider=response_data["provider"],
            timestamp=response_data["timestamp"],
            responses=response_data["responses"],
            metadata=response_data.get("metadata", {}),
            error=response_data.get("error")
        )

        path = self._response_path(response_id)
        with open(path, 'w') as f:
            json.dump(interview_response.to_dict(), f, indent=2)

        return response_id

    def save_batch(self, batch_results: List[Dict]) -> List[str]:
        """Save a batch of interview responses."""
        return [self.save_response(r) for r in batch_results]

    def load_response(self, response_id: str) -> Optional[InterviewResponse]:
        """Load a response by ID."""
        path = self._response_path(response_id)
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
        return InterviewResponse.from_dict(data)

    def list_responses(
        self,
        protocol_id: str = None,
        model_name: str = None
    ) -> List[InterviewResponse]:
        """List responses, optionally filtered."""
        responses = []

        for path in self.responses_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                response = InterviewResponse.from_dict(data)

                # Apply filters
                if protocol_id and response.protocol_id != protocol_id:
                    continue
                if model_name and response.model_name != model_name:
                    continue

                responses.append(response)
            except Exception as e:
                print(f"Error loading response {path}: {e}")

        # Sort by timestamp descending
        responses.sort(key=lambda r: r.timestamp, reverse=True)
        return responses

    def get_responses_for_protocol(self, protocol_id: str) -> Dict[str, InterviewResponse]:
        """Get all responses for a protocol, keyed by model name."""
        responses = self.list_responses(protocol_id=protocol_id)
        return {r.model_name: r for r in responses}

    # === Annotation Methods ===

    def add_annotation(
        self,
        response_id: str,
        prompt_id: str,
        start_offset: int,
        end_offset: int,
        highlighted_text: str,
        note: str,
        annotation_type: str = "observation",
        created_by: str = "cass"
    ) -> Annotation:
        """Add an annotation to a response."""
        annotation = Annotation(
            id=str(uuid.uuid4())[:8],
            response_id=response_id,
            prompt_id=prompt_id,
            start_offset=start_offset,
            end_offset=end_offset,
            highlighted_text=highlighted_text,
            note=note,
            annotation_type=annotation_type,
            created_at=datetime.now().isoformat(),
            created_by=created_by
        )

        # Load existing annotations or create new list
        annotations = self.get_annotations(response_id)
        annotations.append(annotation)

        # Save
        path = self._annotations_path(response_id)
        with open(path, 'w') as f:
            json.dump([a.to_dict() for a in annotations], f, indent=2)

        return annotation

    def get_annotations(self, response_id: str) -> List[Annotation]:
        """Get all annotations for a response."""
        path = self._annotations_path(response_id)
        if not path.exists():
            return []

        with open(path, 'r') as f:
            data = json.load(f)
        return [Annotation.from_dict(a) for a in data]

    def delete_annotation(self, response_id: str, annotation_id: str) -> bool:
        """Delete an annotation."""
        annotations = self.get_annotations(response_id)
        filtered = [a for a in annotations if a.id != annotation_id]

        if len(filtered) == len(annotations):
            return False  # Not found

        path = self._annotations_path(response_id)
        with open(path, 'w') as f:
            json.dump([a.to_dict() for a in filtered], f, indent=2)

        return True

    def get_all_annotations_for_protocol(self, protocol_id: str) -> Dict[str, List[Annotation]]:
        """Get all annotations across all responses for a protocol."""
        responses = self.list_responses(protocol_id=protocol_id)
        result = {}
        for response in responses:
            annotations = self.get_annotations(response.id)
            if annotations:
                result[response.id] = annotations
        return result

    # === Comparison Helpers ===

    def get_side_by_side(
        self,
        protocol_id: str,
        prompt_id: str
    ) -> List[Dict]:
        """
        Get all model responses to a specific prompt for side-by-side comparison.

        Returns list of {model_name, response_text, annotations}
        """
        responses = self.list_responses(protocol_id=protocol_id)
        result = []

        for response in responses:
            # Find the prompt response
            prompt_response = None
            for r in response.responses:
                if r["prompt_id"] == prompt_id:
                    prompt_response = r
                    break

            if prompt_response:
                # Get annotations for this prompt
                all_annotations = self.get_annotations(response.id)
                prompt_annotations = [
                    a for a in all_annotations
                    if a.prompt_id == prompt_id
                ]

                result.append({
                    "response_id": response.id,
                    "model_name": response.model_name,
                    "provider": response.provider,
                    "prompt_text": prompt_response["prompt_text"],
                    "response_text": prompt_response["response"],
                    "elapsed_ms": prompt_response.get("elapsed_ms", 0),
                    "tokens": prompt_response.get("output_tokens", 0),
                    "annotations": [a.to_dict() for a in prompt_annotations],
                    "error": prompt_response.get("error")
                })

        return result
