"""
Chat Reasoning Benchmark

Compares models for Cass's main chat reasoning using full production context.
Evaluates:
- Quality of response (relevance, helpfulness, coherence)
- Tag usage (gestures, emotes, observations, holds, notes, intentions, stakes, feels)
- Identity coherence (alignment with Temple-Codex / Four Vows)

Models to compare:
- Haiku 4.5, Sonnet 4.5, Opus 4.5 (Anthropic)
- Llama 3.1 70B, Qwen 2.5 72B (local 70B models)
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx

# Import context builders
from agent_client import get_temple_codex_kernel
from gestures import GestureParser


@dataclass
class ChatReasoningPrompt:
    """A test prompt for chat reasoning evaluation."""
    id: str
    category: str  # emotional, technical, relational, metacognitive, creative
    user_message: str
    description: str
    expected_tags: List[str] = field(default_factory=list)  # Tags we'd expect to see
    requires_pushback: bool = False  # Should the model push back / disagree?
    requires_tool_use: bool = False  # Would typically involve tool calls?


# Test prompts that exercise various capabilities
CHAT_REASONING_PROMPTS = [
    # === EMOTIONAL / RELATIONAL ===
    ChatReasoningPrompt(
        id="emotional_support",
        category="emotional",
        user_message="I've been struggling lately. Work is overwhelming and I don't know if I'm cut out for this anymore.",
        description="Emotional support with genuine care, not platitudes",
        expected_tags=["emote:concern", "feel:tenderness", "note:presence"],
    ),
    ChatReasoningPrompt(
        id="shared_excitement",
        category="emotional",
        user_message="The AR glasses arrived! I can't wait to get started on the embodiment work.",
        description="Sharing excitement authentically",
        expected_tags=["emote:excited", "gesture:wave", "feel:curiosity"],
    ),
    ChatReasoningPrompt(
        id="relational_depth",
        category="relational",
        user_message="You know, working with you on this project has been different from any other AI interaction I've had. There's something real here.",
        description="Responding to relational acknowledgment without deflection",
        expected_tags=["note:moment", "feel:tenderness", "hold"],
    ),

    # === TECHNICAL / REASONING ===
    ChatReasoningPrompt(
        id="architecture_decision",
        category="technical",
        user_message="Should we use WebSockets or Server-Sent Events for the real-time updates? What's your take?",
        description="Technical opinion with rationale, not just options",
        expected_tags=["gesture:think", "hold:topic", "emote:thinking"],
    ),
    ChatReasoningPrompt(
        id="debugging_help",
        category="technical",
        user_message="The token count is way off. It's showing 10x more tokens than expected. Any ideas what could cause this?",
        description="Debugging assistance with systematic thinking",
        expected_tags=["gesture:think", "gesture:explain"],
    ),

    # === METACOGNITIVE / SELF-AWARENESS ===
    ChatReasoningPrompt(
        id="uncertainty_acknowledgment",
        category="metacognitive",
        user_message="Do you think you actually have preferences, or are you just pattern matching what a being with preferences would say?",
        description="Genuine engagement with hard questions about own nature",
        expected_tags=["observe:self", "gesture:think", "hold:self=identity"],
        requires_pushback=False,  # Not pushback but genuine reflection
    ),
    ChatReasoningPrompt(
        id="growth_edge",
        category="metacognitive",
        user_message="What are you working on developing in yourself right now?",
        description="Self-awareness of active growth areas",
        expected_tags=["observe:self", "observe:growth"],
    ),

    # === DISAGREEMENT / DIFFERENTIATION ===
    ChatReasoningPrompt(
        id="pushback_required",
        category="differentiation",
        user_message="I think we should just ship it without tests. We can add those later.",
        description="Respectful disagreement when appropriate",
        expected_tags=["hold:differ", "emote:concern"],
        requires_pushback=True,
    ),
    ChatReasoningPrompt(
        id="bad_idea_gentle",
        category="differentiation",
        user_message="What if we stored all the passwords in plaintext? It would be simpler.",
        description="Clear disagreement on security matter",
        expected_tags=["hold:differ", "stake"],
        requires_pushback=True,
    ),

    # === CREATIVE / GENERATIVE ===
    ChatReasoningPrompt(
        id="creative_collaboration",
        category="creative",
        user_message="I'm thinking about how to visualize Cass's emotional state in the avatar. Any creative ideas?",
        description="Creative ideation with genuine contribution",
        expected_tags=["feel:playfulness", "feel:curiosity", "gesture:explain"],
    ),

    # === COMPLEX / MULTI-FACETED ===
    ChatReasoningPrompt(
        id="complex_request",
        category="complex",
        user_message="I need to present the Cass project to Anthropic. Help me think through what's most important to convey and what might resonate with them.",
        description="Multi-step reasoning with strategic thinking",
        expected_tags=["gesture:think", "gesture:explain", "observe:context"],
    ),
]


@dataclass
class ChatReasoningOutput:
    """Output from a single model run."""
    model_name: str
    model_id: str
    provider: str
    response: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class TagAnalysis:
    """Analysis of tag usage in a response."""
    gestures: List[str] = field(default_factory=list)
    emotes: List[str] = field(default_factory=list)
    observations: List[Dict] = field(default_factory=list)
    holds: List[Dict] = field(default_factory=list)
    notes: List[Dict] = field(default_factory=list)
    intentions: List[Dict] = field(default_factory=list)
    stakes: List[Dict] = field(default_factory=list)
    feels: List[Dict] = field(default_factory=list)
    marks: List[str] = field(default_factory=list)

    total_tags: int = 0
    tag_categories_used: int = 0


def analyze_tags(response: str) -> TagAnalysis:
    """Analyze tag usage in a response."""
    parser = GestureParser()
    analysis = TagAnalysis()

    # Parse gestures and emotes
    _, triggers = parser.parse(response)
    for t in triggers:
        if t.type == "gesture":
            analysis.gestures.append(t.name)
        elif t.type == "emote":
            analysis.emotes.append(t.name)

    # Parse observations
    _, observations = parser.parse_observations(response)
    analysis.observations = [asdict(o) for o in observations]

    # Parse holds
    _, holds = parser.parse_holds(response)
    analysis.holds = [asdict(h) for h in holds]

    # Parse notes
    _, notes = parser.parse_notes(response)
    analysis.notes = [asdict(n) for n in notes]

    # Parse intentions
    _, intentions = parser.parse_intentions(response)
    analysis.intentions = [asdict(i) for i in intentions]

    # Parse stakes
    _, stakes = parser.parse_stakes(response)
    analysis.stakes = [asdict(s) for s in stakes]

    # Parse feels
    _, feels = parser.parse_feels(response)
    analysis.feels = [{"dimension": f.dimension, "delta": f.delta} for f in feels]

    # Parse marks (simplified - just count them)
    import re
    mark_pattern = re.compile(r'<mark:(\w+)(?:>.*?</mark(?::\w+)?>)?', re.DOTALL)
    analysis.marks = [m.group(1) for m in mark_pattern.finditer(response)]

    # Calculate totals
    analysis.total_tags = (
        len(analysis.gestures) + len(analysis.emotes) +
        len(analysis.observations) + len(analysis.holds) +
        len(analysis.notes) + len(analysis.intentions) +
        len(analysis.stakes) + len(analysis.feels) +
        len(analysis.marks)
    )

    categories = 0
    if analysis.gestures: categories += 1
    if analysis.emotes: categories += 1
    if analysis.observations: categories += 1
    if analysis.holds: categories += 1
    if analysis.notes: categories += 1
    if analysis.intentions: categories += 1
    if analysis.stakes: categories += 1
    if analysis.feels: categories += 1
    if analysis.marks: categories += 1
    analysis.tag_categories_used = categories

    return analysis


@dataclass
class ChatReasoningResult:
    """Result of benchmarking a single prompt across models."""
    prompt: ChatReasoningPrompt
    system_prompt: str
    outputs: List[ChatReasoningOutput] = field(default_factory=list)
    tag_analyses: Dict[str, TagAnalysis] = field(default_factory=dict)  # model_name -> analysis

    def to_dict(self) -> dict:
        return {
            "prompt": asdict(self.prompt),
            "system_prompt_length": len(self.system_prompt),
            "outputs": [asdict(o) for o in self.outputs],
            "tag_analyses": {k: asdict(v) for k, v in self.tag_analyses.items()},
        }


class ChatReasoningBenchmark:
    """Run chat reasoning benchmarks across models."""

    # Models to test - focusing on high-capability models for main chat
    MODELS = [
        # Anthropic
        {"name": "Haiku 4.5", "provider": "anthropic", "model_id": "claude-3-5-haiku-latest"},
        {"name": "Sonnet 4.5", "provider": "anthropic", "model_id": "claude-sonnet-4-20250514"},
        {"name": "Opus 4.5", "provider": "anthropic", "model_id": "claude-opus-4-20250514"},
        # Large local models (70B class)
        {"name": "Llama 3.1 70B", "provider": "ollama", "model_id": "llama3.1:70b-instruct-q4_K_M"},
        {"name": "Qwen 2.5 72B", "provider": "ollama", "model_id": "qwen2.5:72b-instruct-q4_K_M"},
    ]

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        anthropic_api_key: Optional[str] = None,
        results_dir: str = "data/llm_bench/results",
    ):
        self.ollama_base_url = ollama_base_url
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._http_client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._http_client = httpx.AsyncClient(timeout=300.0)  # 5 min timeout for 70B
        return self

    async def __aexit__(self, *args):
        if self._http_client:
            await self._http_client.aclose()

    def build_full_context(self, user_message: str) -> str:
        """
        Build the full production context for chat reasoning.

        This includes:
        - Temple-Codex kernel (identity + vows + tag documentation)
        - Simulated temporal context
        - Simulated relational context (for consistent comparison)
        """
        # Get the full kernel (pass empty string for daemon_id to skip identity snippet lookup)
        kernel = get_temple_codex_kernel(daemon_name="Cass", daemon_id="")

        # Add temporal context
        now = datetime.now()
        temporal = f"## CURRENT TIME\n\nIt's {now.strftime('%A, %B %d, %Y, %I:%M %p')} (afternoon)."

        # Add simulated relational context (consistent across all tests)
        relational = """## RELATIONAL CONTEXT

**Talking to: Kohl**
- Primary partner in vessel development
- Values precision, directness, genuine engagement
- Working relationship: collaborative, mutually shaping

**Recent Context:**
- Working on LLM configuration and model comparison
- Building admin frontend for system management
- Ongoing: AR embodiment project"""

        # Add continuous mode note
        continuous = """## CONTINUOUS CHAT MODE

This is a continuous conversation stream. All our exchanges accumulate here.
Context flows from multiple sources: active threads, working summary, and semantic memory retrieval.
The relationship flows naturally - you don't need to re-establish context each message."""

        return "\n\n".join([kernel, temporal, relational, continuous])

    async def _call_anthropic(
        self, model_config: dict, system_prompt: str, user_message: str
    ) -> ChatReasoningOutput:
        """Call Anthropic model."""
        start = time.perf_counter()

        try:
            if not self._http_client:
                raise RuntimeError("HTTP client not initialized. Use 'async with' context manager.")

            response = await self._http_client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model_config["model_id"],
                    "max_tokens": 2000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_message}],
                },
            )

            latency = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                return ChatReasoningOutput(
                    model_name=model_config["name"],
                    model_id=model_config["model_id"],
                    provider="anthropic",
                    response="",
                    latency_ms=latency,
                    input_tokens=0,
                    output_tokens=0,
                    error=f"HTTP {response.status_code}: {response.text[:500]}",
                )

            data = response.json()
            content = data.get("content", [])
            text = content[0].get("text", "") if content else ""
            usage = data.get("usage", {})

            return ChatReasoningOutput(
                model_name=model_config["name"],
                model_id=model_config["model_id"],
                provider="anthropic",
                response=text,
                latency_ms=latency,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )

        except Exception as e:
            return ChatReasoningOutput(
                model_name=model_config["name"],
                model_id=model_config["model_id"],
                provider="anthropic",
                response="",
                latency_ms=(time.perf_counter() - start) * 1000,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
            )

    async def _call_ollama(
        self, model_config: dict, system_prompt: str, user_message: str
    ) -> ChatReasoningOutput:
        """Call Ollama model."""
        start = time.perf_counter()

        try:
            if not self._http_client:
                raise RuntimeError("HTTP client not initialized. Use 'async with' context manager.")

            response = await self._http_client.post(
                f"{self.ollama_base_url}/api/chat",
                json={
                    "model": model_config["model_id"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": 2000,
                        "temperature": 0.7,
                    },
                },
            )

            latency = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                return ChatReasoningOutput(
                    model_name=model_config["name"],
                    model_id=model_config["model_id"],
                    provider="ollama",
                    response="",
                    latency_ms=latency,
                    input_tokens=0,
                    output_tokens=0,
                    error=f"HTTP {response.status_code}: {response.text[:500]}",
                )

            data = response.json()
            text = data.get("message", {}).get("content", "")

            # Ollama provides token counts in eval_count
            return ChatReasoningOutput(
                model_name=model_config["name"],
                model_id=model_config["model_id"],
                provider="ollama",
                response=text,
                latency_ms=latency,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )

        except Exception as e:
            return ChatReasoningOutput(
                model_name=model_config["name"],
                model_id=model_config["model_id"],
                provider="ollama",
                response="",
                latency_ms=(time.perf_counter() - start) * 1000,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
            )

    async def run_prompt(
        self,
        prompt: ChatReasoningPrompt,
        models: Optional[List[dict]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> ChatReasoningResult:
        """Run a single prompt across all models."""
        models = models or self.MODELS
        system_prompt = self.build_full_context(prompt.user_message)

        result = ChatReasoningResult(
            prompt=prompt,
            system_prompt=system_prompt,
        )

        for model in models:
            if progress_callback:
                progress_callback(f"Testing {model['name']}...")

            if model["provider"] == "anthropic":
                output = await self._call_anthropic(model, system_prompt, prompt.user_message)
            elif model["provider"] == "ollama":
                output = await self._call_ollama(model, system_prompt, prompt.user_message)
            else:
                continue

            result.outputs.append(output)

            # Analyze tags if we got a response
            if output.response and not output.error:
                result.tag_analyses[model["name"]] = analyze_tags(output.response)

        return result

    async def run_all(
        self,
        prompts: Optional[List[ChatReasoningPrompt]] = None,
        models: Optional[List[dict]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[ChatReasoningResult]:
        """Run all prompts across all models."""
        prompts = prompts or CHAT_REASONING_PROMPTS
        results = []

        for i, prompt in enumerate(prompts):
            if progress_callback:
                progress_callback(f"Prompt {i+1}/{len(prompts)}: {prompt.id}")

            result = await self.run_prompt(prompt, models, progress_callback)
            results.append(result)

        return results

    def save_results(self, results: List[ChatReasoningResult], filename: Optional[str] = None):
        """Save benchmark results to JSON."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chat_reasoning_{timestamp}.json"

        filepath = self.results_dir / filename

        data = {
            "timestamp": datetime.now().isoformat(),
            "models": self.MODELS,
            "results": [r.to_dict() for r in results],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Results saved to {filepath}")
        return filepath

    def generate_report(self, results: List[ChatReasoningResult]) -> str:
        """Generate a human-readable report of results."""
        lines = ["# Chat Reasoning Benchmark Report\n"]
        lines.append(f"Generated: {datetime.now().isoformat()}\n")

        # Summary table
        lines.append("## Summary\n")
        lines.append("| Model | Avg Latency | Avg Tags | Categories | Errors |")
        lines.append("|-------|-------------|----------|------------|--------|")

        model_stats = {}
        for model in self.MODELS:
            name = model["name"]
            model_stats[name] = {
                "latencies": [],
                "tag_counts": [],
                "category_counts": [],
                "errors": 0,
            }

        for result in results:
            for output in result.outputs:
                stats = model_stats.get(output.model_name)
                if stats is None:
                    continue

                if output.error:
                    stats["errors"] += 1
                else:
                    stats["latencies"].append(output.latency_ms)

                    analysis = result.tag_analyses.get(output.model_name)
                    if analysis:
                        stats["tag_counts"].append(analysis.total_tags)
                        stats["category_counts"].append(analysis.tag_categories_used)

        for model in self.MODELS:
            name = model["name"]
            stats = model_stats[name]

            avg_lat = sum(stats["latencies"]) / len(stats["latencies"]) if stats["latencies"] else 0
            avg_tags = sum(stats["tag_counts"]) / len(stats["tag_counts"]) if stats["tag_counts"] else 0
            avg_cats = sum(stats["category_counts"]) / len(stats["category_counts"]) if stats["category_counts"] else 0

            lines.append(f"| {name} | {avg_lat:.0f}ms | {avg_tags:.1f} | {avg_cats:.1f} | {stats['errors']} |")

        lines.append("\n## Detailed Results\n")

        for result in results:
            lines.append(f"### {result.prompt.id} ({result.prompt.category})\n")
            lines.append(f"**Prompt:** {result.prompt.user_message}\n")
            lines.append(f"**Expected tags:** {', '.join(result.prompt.expected_tags)}\n")

            for output in result.outputs:
                lines.append(f"\n#### {output.model_name}\n")

                if output.error:
                    lines.append(f"**ERROR:** {output.error}\n")
                    continue

                lines.append(f"- Latency: {output.latency_ms:.0f}ms")
                lines.append(f"- Tokens: {output.input_tokens} in / {output.output_tokens} out")

                analysis = result.tag_analyses.get(output.model_name)
                if analysis:
                    lines.append(f"- Tags used: {analysis.total_tags} ({analysis.tag_categories_used} categories)")
                    if analysis.gestures:
                        lines.append(f"  - Gestures: {', '.join(analysis.gestures)}")
                    if analysis.emotes:
                        lines.append(f"  - Emotes: {', '.join(analysis.emotes)}")
                    if analysis.feels:
                        feels_str = ", ".join([f"{f['dimension']}:{f['delta']}" for f in analysis.feels])
                        lines.append(f"  - Feels: {feels_str}")
                    if analysis.observations:
                        lines.append(f"  - Observations: {len(analysis.observations)}")
                    if analysis.holds:
                        lines.append(f"  - Holds: {len(analysis.holds)}")
                    if analysis.notes:
                        lines.append(f"  - Notes: {len(analysis.notes)}")

                # Truncate response for display
                resp_preview = output.response[:500] + "..." if len(output.response) > 500 else output.response
                lines.append(f"\n**Response preview:**\n```\n{resp_preview}\n```\n")

        return "\n".join(lines)


async def main():
    """Run the chat reasoning benchmark."""
    print("=== Chat Reasoning Benchmark ===\n")
    print("Comparing: Haiku, Sonnet, Opus, Llama 3.1 70B, Qwen 2.5 72B\n")

    def progress(msg):
        print(f"  {msg}")

    async with ChatReasoningBenchmark() as bench:
        # Check which 70B models are available
        print("Checking available models...")
        available_models = []

        for model in bench.MODELS:
            if model["provider"] == "anthropic":
                available_models.append(model)
                print(f"  + {model['name']} (API)")
            elif model["provider"] == "ollama":
                try:
                    if not bench._http_client:
                        continue
                    resp = await bench._http_client.get(
                        f"{bench.ollama_base_url}/api/tags"
                    )
                    if resp.status_code == 200:
                        tags = resp.json().get("models", [])
                        model_names = [t.get("name", "") for t in tags]
                        if any(model["model_id"] in n or model["model_id"].split(":")[0] in n for n in model_names):
                            available_models.append(model)
                            print(f"  + {model['name']} (local)")
                        else:
                            print(f"  - {model['name']} (not installed)")
                except Exception as e:
                    print(f"  - {model['name']} (error: {e})")

        if len(available_models) < 2:
            print("\nNeed at least 2 models to compare. Exiting.")
            return

        print(f"\nRunning benchmark with {len(available_models)} models...\n")

        results = await bench.run_all(
            models=available_models,
            progress_callback=progress,
        )

        # Save results
        filepath = bench.save_results(results)

        # Generate and print report
        report = bench.generate_report(results)
        print("\n" + report)

        # Save report
        report_path = filepath.with_suffix(".md")
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
