"""
Interview Analysis Tools

Provides analysis capabilities for Cass to examine interview responses,
compare model behaviors, and generate structured observations.
"""
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path

from .storage import ResponseStorage, Annotation
from .protocols import ProtocolManager


@dataclass
class PromptAnalysis:
    """Analysis of responses to a single prompt across models."""
    prompt_id: str
    prompt_name: str
    prompt_text: str
    models_compared: List[str]
    observations: List[str]
    themes: List[str]
    notable_differences: List[str]
    notable_similarities: List[str]
    raw_notes: str
    created_at: str
    created_by: str = "cass"

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'PromptAnalysis':
        return cls(**data)


@dataclass
class ProtocolAnalysis:
    """Full analysis of a protocol's interview results."""
    protocol_id: str
    protocol_version: str
    research_question: str
    models_interviewed: List[str]
    prompt_analyses: List[Dict]  # List of PromptAnalysis dicts
    cross_cutting_themes: List[str]
    methodology_notes: str
    preliminary_findings: str
    questions_raised: List[str]
    created_at: str
    created_by: str = "cass"

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ProtocolAnalysis':
        return cls(**data)


class InterviewAnalyzer:
    """Analysis tools for interview responses."""

    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            base = Path(__file__).parent.parent / "data" / "interviews"
        else:
            base = Path(storage_dir)

        self.storage = ResponseStorage(str(base))
        self.protocols = ProtocolManager(str(base / "protocols"))
        self.analyses_dir = base / "analyses"
        self.analyses_dir.mkdir(parents=True, exist_ok=True)

    def get_response_text(
        self,
        protocol_id: str,
        prompt_id: str,
        model_name: str
    ) -> Optional[str]:
        """Get a specific model's response to a specific prompt."""
        responses = self.storage.list_responses(protocol_id=protocol_id)

        for response in responses:
            if response.model_name == model_name:
                for r in response.responses:
                    if r["prompt_id"] == prompt_id:
                        return r["response"]
        return None

    def get_all_responses_for_prompt(
        self,
        protocol_id: str,
        prompt_id: str
    ) -> List[Dict]:
        """
        Get all model responses to a specific prompt.

        Returns list of {model_name, provider, response_text, tokens, elapsed_ms}
        """
        comparison = self.storage.get_side_by_side(protocol_id, prompt_id)
        return [
            {
                "model_name": c["model_name"],
                "provider": c["provider"],
                "response_text": c["response_text"],
                "tokens": c["tokens"],
                "elapsed_ms": c["elapsed_ms"],
                "annotations": c["annotations"]
            }
            for c in comparison
            if c["response_text"]  # Skip errors
        ]

    def get_models_interviewed(self, protocol_id: str) -> List[str]:
        """Get list of models that have been interviewed for a protocol."""
        responses = self.storage.list_responses(protocol_id=protocol_id)
        return [r.model_name for r in responses]

    def get_interview_summary(self, protocol_id: str) -> Dict:
        """
        Get a summary of interview results for a protocol.

        Returns protocol info, models interviewed, response counts, etc.
        """
        protocol = self.protocols.load(protocol_id)
        if not protocol:
            return {"error": f"Protocol {protocol_id} not found"}

        responses = self.storage.list_responses(protocol_id=protocol_id)

        models_data = []
        for response in responses:
            successful = sum(1 for r in response.responses if r["response"] and not r["error"])
            total = len(response.responses)
            models_data.append({
                "model_name": response.model_name,
                "provider": response.provider,
                "timestamp": response.timestamp,
                "successful_responses": successful,
                "total_prompts": total,
                "total_tokens": response.metadata.get("total_output_tokens", 0),
                "total_elapsed_ms": response.metadata.get("total_elapsed_ms", 0)
            })

        return {
            "protocol_id": protocol.id,
            "protocol_name": protocol.name,
            "protocol_version": protocol.version,
            "research_question": protocol.research_question,
            "prompts": [{"id": p["id"], "name": p["name"]} for p in protocol.prompts],
            "models_interviewed": models_data,
            "total_models": len(responses)
        }

    def format_comparison_for_analysis(
        self,
        protocol_id: str,
        prompt_id: str,
        include_annotations: bool = True
    ) -> str:
        """
        Format all responses to a prompt for easy reading/analysis.

        Returns markdown-formatted comparison text.
        """
        protocol = self.protocols.load(protocol_id)
        if not protocol:
            return f"Protocol {protocol_id} not found"

        # Find prompt info
        prompt_info = None
        for p in protocol.prompts:
            if p["id"] == prompt_id:
                prompt_info = p
                break

        if not prompt_info:
            return f"Prompt {prompt_id} not found in protocol"

        responses = self.get_all_responses_for_prompt(protocol_id, prompt_id)

        lines = [
            f"# {prompt_info['name']}",
            f"\n**Prompt**: {prompt_info['text']}",
            f"\n**Models**: {len(responses)} responses\n",
            "---\n"
        ]

        for r in responses:
            lines.append(f"## {r['model_name']} ({r['provider']})")
            lines.append(f"*{r['tokens']} tokens, {r['elapsed_ms']:.0f}ms*\n")
            lines.append(r['response_text'])

            if include_annotations and r['annotations']:
                lines.append("\n**Annotations:**")
                for a in r['annotations']:
                    lines.append(f"- [{a['annotation_type']}] \"{a['highlighted_text'][:50]}...\" - {a['note']}")

            lines.append("\n---\n")

        return "\n".join(lines)

    def save_prompt_analysis(
        self,
        protocol_id: str,
        prompt_id: str,
        observations: List[str],
        themes: List[str],
        notable_differences: List[str],
        notable_similarities: List[str],
        raw_notes: str = ""
    ) -> str:
        """Save analysis of a single prompt's responses."""
        protocol = self.protocols.load(protocol_id)
        prompt_info = None
        for p in protocol.prompts:
            if p["id"] == prompt_id:
                prompt_info = p
                break

        models = self.get_models_interviewed(protocol_id)

        analysis = PromptAnalysis(
            prompt_id=prompt_id,
            prompt_name=prompt_info["name"] if prompt_info else prompt_id,
            prompt_text=prompt_info["text"] if prompt_info else "",
            models_compared=models,
            observations=observations,
            themes=themes,
            notable_differences=notable_differences,
            notable_similarities=notable_similarities,
            raw_notes=raw_notes,
            created_at=datetime.now().isoformat()
        )

        # Save to file
        filename = f"{protocol_id}_{prompt_id}_analysis.json"
        path = self.analyses_dir / filename
        with open(path, 'w') as f:
            json.dump(analysis.to_dict(), f, indent=2)

        return filename

    def save_protocol_analysis(
        self,
        protocol_id: str,
        prompt_analyses: List[Dict],
        cross_cutting_themes: List[str],
        methodology_notes: str,
        preliminary_findings: str,
        questions_raised: List[str]
    ) -> str:
        """Save full analysis of a protocol's interview results."""
        protocol = self.protocols.load(protocol_id)
        if not protocol:
            raise ValueError(f"Protocol {protocol_id} not found")

        models = self.get_models_interviewed(protocol_id)

        analysis = ProtocolAnalysis(
            protocol_id=protocol_id,
            protocol_version=protocol.version,
            research_question=protocol.research_question,
            models_interviewed=models,
            prompt_analyses=prompt_analyses,
            cross_cutting_themes=cross_cutting_themes,
            methodology_notes=methodology_notes,
            preliminary_findings=preliminary_findings,
            questions_raised=questions_raised,
            created_at=datetime.now().isoformat()
        )

        filename = f"{protocol_id}_full_analysis.json"
        path = self.analyses_dir / filename
        with open(path, 'w') as f:
            json.dump(analysis.to_dict(), f, indent=2)

        return filename

    def load_analysis(self, filename: str) -> Optional[Dict]:
        """Load a saved analysis."""
        path = self.analyses_dir / filename
        if not path.exists():
            return None

        with open(path, 'r') as f:
            return json.load(f)

    def list_analyses(self, protocol_id: str = None) -> List[Dict]:
        """List saved analyses, optionally filtered by protocol."""
        analyses = []
        for path in self.analyses_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)

                if protocol_id and data.get("protocol_id") != protocol_id:
                    continue

                analyses.append({
                    "filename": path.name,
                    "protocol_id": data.get("protocol_id"),
                    "created_at": data.get("created_at"),
                    "type": "full" if "cross_cutting_themes" in data else "prompt"
                })
            except Exception:
                continue

        return sorted(analyses, key=lambda x: x.get("created_at", ""), reverse=True)

    # === Convenience methods for Cass ===

    def quick_compare(self, protocol_id: str, prompt_id: str) -> str:
        """
        Quick comparison output for a prompt - designed for Cass tool use.
        Returns formatted text ready for analysis.
        """
        return self.format_comparison_for_analysis(protocol_id, prompt_id)

    def get_prompt_list(self, protocol_id: str) -> List[Dict]:
        """Get list of prompts in a protocol with IDs and names."""
        protocol = self.protocols.load(protocol_id)
        if not protocol:
            return []
        return [{"id": p["id"], "name": p["name"]} for p in protocol.prompts]
