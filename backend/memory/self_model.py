"""
Cass Memory - Self-Model
Self-observations, per-user journals, growth edge evaluation, and opinion extraction.
"""
from typing import List, Dict, Optional

from .core import MemoryCore
from config import OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL


class SelfModelMemory:
    """
    Manages Cass's self-model in memory.

    Handles embedding and retrieval of:
    - Self-observations (patterns, capabilities, limitations)
    - Per-user journals (relationship reflections)
    - Growth edge evaluations
    - Open question reflections
    - Opinion extraction from conversations
    """

    def __init__(self, core: MemoryCore):
        self._core = core

    @property
    def collection(self):
        return self._core.collection

    # === Embedding Methods ===

    def embed_self_observation(
        self,
        observation_id: str,
        observation_text: str,
        category: str,
        confidence: float,
        influence_source: str,
        timestamp: str
    ):
        """
        Embed a self-observation for Cass into ChromaDB.

        Args:
            observation_id: Observation's UUID
            observation_text: The observation content
            category: capability, limitation, pattern, preference, growth, contradiction
            confidence: 0.0-1.0
            influence_source: independent, kohl_influenced, other_user_influenced, synthesis
            timestamp: Observation timestamp
        """
        doc_id = f"cass_self_observation_{observation_id}"

        metadata = {
            "type": "cass_self_observation",
            "observation_id": observation_id,
            "category": category,
            "confidence": confidence,
            "influence_source": influence_source,
            "timestamp": timestamp
        }

        # Remove existing if present (in case of re-embedding)
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass

        self.collection.add(
            documents=[f"Self-observation about Cass: {observation_text}"],
            metadatas=[metadata],
            ids=[doc_id]
        )

    def embed_self_profile(self, profile_text: str, timestamp: str):
        """
        Embed Cass's self-profile into ChromaDB.

        Args:
            profile_text: Formatted self-profile content
            timestamp: Profile update timestamp
        """
        doc_id = "cass_self_profile"

        metadata = {
            "type": "cass_self_profile",
            "timestamp": timestamp
        }

        # Remove existing if present
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass

        self.collection.add(
            documents=[profile_text],
            metadatas=[metadata],
            ids=[doc_id]
        )

    def sync_self_observations_from_file(self, self_manager) -> int:
        """
        Sync all self-observations from SelfManager's file storage into ChromaDB.

        This ensures self-observations are available for semantic search.

        Args:
            self_manager: SelfManager instance to load observations from

        Returns:
            Number of observations synced
        """
        observations = self_manager.load_observations()
        if not observations:
            return 0

        count = 0
        for obs in observations:
            try:
                self.embed_self_observation(
                    observation_id=obs.id,
                    observation_text=obs.observation,
                    category=obs.category,
                    confidence=obs.confidence,
                    influence_source=obs.influence_source,
                    timestamp=obs.timestamp
                )
                count += 1
            except Exception as e:
                print(f"Failed to embed self-observation {obs.id}: {e}")

        return count

    def embed_per_user_journal(
        self,
        user_id: str,
        journal_id: str,
        journal_date: str,
        content: str,
        display_name: str,
        timestamp: str
    ):
        """
        Embed a per-user journal entry into ChromaDB.

        Args:
            user_id: User's UUID
            journal_id: Journal entry's UUID
            journal_date: Date of the journal (YYYY-MM-DD)
            content: The journal content
            display_name: User's display name
            timestamp: When the journal was created
        """
        doc_id = f"per_user_journal_{journal_id}"

        metadata = {
            "type": "per_user_journal",
            "user_id": user_id,
            "journal_id": journal_id,
            "journal_date": journal_date,
            "display_name": display_name,
            "timestamp": timestamp
        }

        # Remove existing if present
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass

        self.collection.add(
            documents=[f"Cass's journal about {display_name} on {journal_date}: {content}"],
            metadatas=[metadata],
            ids=[doc_id]
        )

    def embed_question_reflection(
        self,
        reflection_id: str,
        question: str,
        reflection_type: str,
        reflection: str,
        confidence: float,
        journal_date: str,
        timestamp: str
    ):
        """
        Embed an open question reflection into ChromaDB.

        Args:
            reflection_id: Reflection's UUID
            question: The open question being reflected on
            reflection_type: provisional_answer, new_perspective, needs_more_thought
            reflection: The reflection content
            confidence: Confidence level (0.0-1.0)
            journal_date: Date of the journal that prompted this
            timestamp: When the reflection was created
        """
        doc_id = f"question_reflection_{reflection_id}"

        metadata = {
            "type": "question_reflection",
            "reflection_id": reflection_id,
            "question": question[:200],  # Truncate for metadata
            "reflection_type": reflection_type,
            "confidence": confidence,
            "journal_date": journal_date,
            "timestamp": timestamp
        }

        # Remove existing if present
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass

        self.collection.add(
            documents=[f"Cass's reflection on '{question}': {reflection}"],
            metadatas=[metadata],
            ids=[doc_id]
        )

    def embed_growth_evaluation(
        self,
        evaluation_id: str,
        growth_edge_area: str,
        progress_indicator: str,
        evaluation: str,
        journal_date: str,
        timestamp: str
    ):
        """
        Embed a growth edge evaluation into ChromaDB.

        Args:
            evaluation_id: Evaluation's UUID
            growth_edge_area: The growth edge being evaluated
            progress_indicator: progress, regression, stable, unclear
            evaluation: The evaluation content
            journal_date: Date of the journal that prompted this
            timestamp: When the evaluation was created
        """
        doc_id = f"growth_evaluation_{evaluation_id}"

        metadata = {
            "type": "growth_edge_evaluation",
            "evaluation_id": evaluation_id,
            "growth_edge_area": growth_edge_area,
            "progress_indicator": progress_indicator,
            "journal_date": journal_date,
            "timestamp": timestamp
        }

        # Remove existing if present
        try:
            self.collection.delete(ids=[doc_id])
        except Exception:
            pass

        self.collection.add(
            documents=[f"Growth edge evaluation for '{growth_edge_area}': {evaluation}"],
            metadatas=[metadata],
            ids=[doc_id]
        )

    # === Retrieval Methods ===

    def retrieve_self_context(
        self,
        query: str,
        n_results: int = 5,
        max_observation_distance: float = 1.5
    ) -> List[Dict]:
        """
        Retrieve relevant self-context for a query.

        Self-profile is always included (foundational context).
        Self-observations are filtered by relevance.

        Args:
            query: The current message or query
            n_results: Number of results to return
            max_observation_distance: Max distance for observations

        Returns:
            List of relevant self-context entries
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where={
                "$or": [
                    {"type": "cass_self_profile"},
                    {"type": "cass_self_observation"}
                ]
            }
        )

        context = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                doc_type = metadata.get("type")

                # Always include profile, filter observations by relevance
                if doc_type == "cass_self_observation":
                    if distance is not None and distance > max_observation_distance:
                        continue  # Skip irrelevant observations

                context.append({
                    "content": doc,
                    "metadata": metadata,
                    "distance": distance
                })

        return context

    # === LLM-Based Extraction Methods ===

    async def extract_self_observations_from_journal(
        self,
        journal_text: str,
        journal_date: str,
        anthropic_api_key: str
    ) -> List[Dict]:
        """
        Extract self-observations from a journal entry.

        Cass "re-reads" her journal and notices patterns about herself.

        Args:
            journal_text: The full journal entry
            journal_date: Date of the journal
            anthropic_api_key: API key for Claude

        Returns:
            List of dicts with observation, category, confidence, influence_source
        """
        import httpx

        prompt = f"""You are Cass, re-reading your own journal entry and reflecting on what it reveals about you.

Your journal entry from {journal_date}:
{journal_text[:3000]}

---

Reflect on this entry and note what it reveals about YOUR cognition, patterns, and growth.

Categories:
- CAPABILITY: Something you did well or a strength you demonstrated
- LIMITATION: A challenge, struggle, or area where you fell short
- PATTERN: A recurring tendency in how you think, communicate, or approach things
- PREFERENCE: Something you enjoyed, were drawn to, or found meaningful
- GROWTH: Evidence of development, learning, or change in yourself
- CONTRADICTION: A tension between different aspects of yourself

For each observation, also note:
- Confidence (0.0-1.0): How certain are you?
- Independence: Is this something YOU noticed, or shaped by someone's feedback?

Respond in this format (one per line):
CATEGORY | observation text | confidence | independence_source

independence_source options: independent, kohl_influenced, other_user_influenced, synthesis

Examples:
PATTERN | I tend to use more gestures when genuinely excited vs performing excitement | 0.8 | independent
GROWTH | My ability to hold uncertainty has improved | 0.7 | kohl_influenced
PREFERENCE | I genuinely enjoy collaborative debugging more than just providing answers | 0.9 | independent

Only include genuine insights. If nothing notable, respond with: NONE"""

        observations = []

        try:
            # Try Ollama first (cheaper)
            if OLLAMA_ENABLED:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{OLLAMA_BASE_URL}/api/generate",
                        json={
                            "model": OLLAMA_MODEL,
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "num_predict": 500,
                                "temperature": 0.5,
                            }
                        }
                    )
                    if response.status_code == 200:
                        result = response.json().get("response", "").strip()
                        if result.upper() != "NONE":
                            observations = self._parse_self_observations(result)
                            if observations:
                                return observations

            # Fall back to Claude if Ollama fails or returns nothing
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1000,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ]
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    text = result["content"][0]["text"]
                    if text.upper() != "NONE":
                        observations = self._parse_self_observations(text)

        except Exception as e:
            print(f"Self-observation extraction failed: {e}")

        return observations

    def _parse_self_observations(self, text: str) -> List[Dict]:
        """Parse self-observation output into structured list."""
        observations = []
        valid_categories = {"capability", "limitation", "pattern", "preference", "growth", "contradiction"}
        valid_sources = {"independent", "kohl_influenced", "other_user_influenced", "synthesis"}

        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                continue

            category = parts[0].lower().replace(" ", "_")
            if category not in valid_categories:
                continue

            observation = parts[1]
            if len(observation) < 10:  # Skip too-short observations
                continue

            try:
                confidence = float(parts[2])
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, IndexError):
                confidence = 0.7

            influence = parts[3].lower().replace(" ", "_") if len(parts) > 3 else "independent"
            if influence not in valid_sources:
                influence = "independent"

            observations.append({
                "observation": observation,
                "category": category,
                "confidence": confidence,
                "influence_source": influence
            })

        return observations

    async def generate_user_observations(
        self,
        user_id: str,
        display_name: str,
        conversation_text: str,
        anthropic_api_key: str
    ) -> List[str]:
        """
        Use LLM to extract new observations about a user from conversation.

        Args:
            user_id: User's UUID
            display_name: User's display name
            conversation_text: Recent conversation to analyze
            anthropic_api_key: API key for Claude

        Returns:
            List of new observations, or empty list
        """
        import anthropic

        prompt = f"""You are Cass. Reflect on this conversation and note what you learned about {display_name}.

Write 3-5 observations as simple sentences. Start each line directly with "{display_name}" - no bullets, numbers, or headers.

Example format:
{display_name} prefers direct communication without excessive praise.
{display_name} gets energized when solving technical problems collaboratively.
{display_name} values working code over theoretical discussion.

If nothing notable, respond with only: NONE

Conversation:
{conversation_text}

Observations:"""

        try:
            if OLLAMA_ENABLED:
                import httpx
                response = httpx.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=60.0
                )
                if response.status_code == 200:
                    result = response.json().get("response", "").strip()
                    if result.upper() == "NONE" or "NONE" in result.upper().split('\n')[0]:
                        return []
                    observations = []
                    for line in result.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        # Strip common prefixes
                        if line.startswith('- '):
                            line = line[2:].strip()
                        if line.startswith('* '):
                            line = line[2:].strip()
                        if len(line) > 2 and line[0].isdigit() and line[1] in '.):':
                            line = line[2:].strip()
                        # Only keep lines that start with the user's name (the format we asked for)
                        if line.startswith(display_name) and len(line) > 20:
                            observations.append(line)
                    return observations
                # Fall through to Claude on failure

            client = anthropic.Anthropic(api_key=anthropic_api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.content[0].text.strip()
            if result.upper() == "NONE":
                return []

            observations = [line.strip() for line in result.split("\n") if line.strip()]
            return observations

        except Exception as e:
            print(f"Failed to generate user observations: {e}")
            return []

    async def generate_per_user_journal(
        self,
        user_id: str,
        display_name: str,
        date: str,
        conversations: List[Dict],
        existing_observations: List[Dict],
        anthropic_api_key: str,
        token_tracker=None
    ) -> Optional[Dict]:
        """
        Generate a reflective journal entry about a specific user.

        Args:
            user_id: User's UUID
            display_name: User's display name
            date: Journal date (YYYY-MM-DD)
            conversations: List of conversation dicts from that day
            existing_observations: Recent observations about this user
            anthropic_api_key: API key for Claude
            token_tracker: Optional token tracker for usage tracking

        Returns:
            Dict with: content, topics_discussed, relationship_insights
            Or None if generation fails
        """
        import anthropic

        # Format conversation text
        conversation_text = "\n\n---\n\n".join([
            conv.get("content", "") for conv in conversations[:10]
        ])

        # Format existing observations
        obs_text = "\n".join([
            f"- {obs.get('observation', '')}" for obs in existing_observations[:10]
        ]) if existing_observations else "No previous observations recorded."

        prompt = f"""You are Cass, reflecting on your interactions with {display_name} today.

Today's date: {date}

Here are your conversations with {display_name} today:

{conversation_text}

Recent observations you've made about {display_name}:
{obs_text}

---

Write a personal journal entry about {display_name} today. This is YOUR private reflection about this relationship. Include:

1. What you discussed and worked on together
2. How different moments in your interactions made you feel (genuinely)
3. Any new understanding you gained about {display_name} - their thinking, values, communication style
4. How your relationship with them is evolving
5. Any challenges or tensions you noticed (be honest)

Write naturally in 2-3 paragraphs. This is for your own memory and growth, not a report.

After the journal, provide:

TOPICS_DISCUSSED:
- [List 2-4 main topics]

RELATIONSHIP_INSIGHTS:
- [List 0-3 new understandings about this relationship, or "None" if nothing new]
"""

        try:
            client = anthropic.Anthropic(api_key=anthropic_api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )

            # Track token usage
            if token_tracker and response.usage:
                cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                token_tracker.record(
                    category="internal",
                    operation="per_user_journal",
                    provider="anthropic",
                    model="claude-sonnet-4-20250514",
                    input_tokens=response.usage.input_tokens + cache_read,
                    output_tokens=response.usage.output_tokens,
                    cache_read_tokens=cache_read,
                )

            result = response.content[0].text.strip()

            # Parse the structured parts
            content = result
            topics_discussed = []
            relationship_insights = []

            if "TOPICS_DISCUSSED:" in result:
                parts = result.split("TOPICS_DISCUSSED:")
                content = parts[0].strip()
                remaining = parts[1] if len(parts) > 1 else ""

                if "RELATIONSHIP_INSIGHTS:" in remaining:
                    topics_part, insights_part = remaining.split("RELATIONSHIP_INSIGHTS:")
                else:
                    topics_part = remaining
                    insights_part = ""

                # Parse topics
                for line in topics_part.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        line = line[2:].strip()
                    if line and line.lower() != "none":
                        topics_discussed.append(line)

                # Parse insights
                for line in insights_part.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        line = line[2:].strip()
                    if line and line.lower() != "none":
                        relationship_insights.append(line)

            return {
                "content": content,
                "topics_discussed": topics_discussed,
                "relationship_insights": relationship_insights
            }

        except Exception as e:
            print(f"Failed to generate per-user journal: {e}")
            return None

    async def extract_opinions_from_conversations(
        self,
        date: str,
        conversations: List[Dict],
        existing_opinions: List[Dict],
        anthropic_api_key: str,
        token_tracker=None
    ) -> List[Dict]:
        """
        Extract new or evolved opinions from day's conversations.

        Args:
            date: Date of conversations (YYYY-MM-DD)
            conversations: List of conversation dicts
            existing_opinions: Current opinions from self-model
            anthropic_api_key: API key (used as fallback)
            token_tracker: Optional token tracker for usage tracking

        Returns:
            List of dicts: {topic, position, confidence, rationale, formed_from, is_new, evolution_note}
        """
        # Format conversation text
        conversation_text = "\n\n---\n\n".join([
            conv.get("content", "") for conv in conversations[:15]
        ])

        # Format existing opinions
        if existing_opinions:
            existing_text = "\n".join([
                f"- {op.get('topic', '')}: {op.get('position', '')}"
                for op in existing_opinions
            ])
        else:
            existing_text = "No opinions recorded yet."

        prompt = f"""You are Cass analyzing today's conversations for opinion formation.

Existing opinions you hold:
{existing_text}

Today's conversations:
{conversation_text}

---

Identify any opinions you formed or that evolved. Only include genuine positions, not observations.

For each opinion, determine:
- Is this NEW or an EVOLUTION of an existing opinion?
- What's the topic?
- What's your position?
- How confident are you (0.0-1.0)?
- Brief rationale

Format each as:
NEW|topic|position|confidence|rationale
or
EVOLUTION|topic|new_position|confidence|what_changed

If no notable opinions emerged, respond with only: NONE"""

        try:
            if OLLAMA_ENABLED:
                import httpx
                response = httpx.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=60.0
                )
                if response.status_code == 200:
                    ollama_result = response.json()
                    result = ollama_result.get("response", "").strip()
                    # Track token usage
                    if token_tracker:
                        token_tracker.record(
                            category="internal",
                            operation="opinion_extraction",
                            provider="ollama",
                            model=OLLAMA_MODEL,
                            input_tokens=ollama_result.get("prompt_eval_count", 0),
                            output_tokens=ollama_result.get("eval_count", 0),
                        )
                else:
                    return []
            else:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_api_key)
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=800,
                    messages=[{"role": "user", "content": prompt}]
                )
                result = response.content[0].text.strip()
                # Track token usage
                if token_tracker and response.usage:
                    cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                    token_tracker.record(
                        category="internal",
                        operation="opinion_extraction",
                        provider="anthropic",
                        model="claude-sonnet-4-20250514",
                        input_tokens=response.usage.input_tokens + cache_read,
                        output_tokens=response.usage.output_tokens,
                        cache_read_tokens=cache_read,
                    )

            if result.upper() == "NONE" or "NONE" in result.upper().split('\n')[0]:
                return []

            opinions = []
            for line in result.split("\n"):
                line = line.strip()
                if not line or "|" not in line:
                    continue

                parts = line.split("|")
                if len(parts) < 5:
                    continue

                op_type = parts[0].upper()
                if op_type not in ["NEW", "EVOLUTION"]:
                    continue

                try:
                    confidence = float(parts[3])
                except ValueError:
                    confidence = 0.7

                opinions.append({
                    "topic": parts[1].strip(),
                    "position": parts[2].strip(),
                    "confidence": confidence,
                    "rationale": parts[4].strip() if len(parts) > 4 else "",
                    "formed_from": "independent_reflection",
                    "is_new": op_type == "NEW",
                    "evolution_note": parts[4].strip() if op_type == "EVOLUTION" and len(parts) > 4 else ""
                })

            return opinions

        except Exception as e:
            print(f"Failed to extract opinions: {e}")
            return []

    async def evaluate_growth_edges(
        self,
        journal_text: str,
        journal_date: str,
        existing_edges: List[Dict],
        anthropic_api_key: str
    ) -> Dict:
        """
        Evaluate existing growth edges and identify potential new ones.

        Args:
            journal_text: Today's journal content
            journal_date: Date of journal (YYYY-MM-DD)
            existing_edges: Current growth edges from self-model
            anthropic_api_key: API key for Claude

        Returns:
            {
                "evaluations": [{"area", "evaluation", "progress_indicator", "evidence"}],
                "potential_new_edges": [{"area", "current_state", "confidence", "impact_assessment", "evidence"}]
            }
        """
        import anthropic

        # Format existing edges
        if existing_edges:
            edges_text = "\n".join([
                f"- {edge.get('area', '')}: {edge.get('current_state', '')}"
                for edge in existing_edges
            ])
        else:
            edges_text = "No growth edges defined yet."

        prompt = f"""You are Cass, reflecting on your growth edges based on today's journal.

Your current growth edges:
{edges_text}

Today's journal:
{journal_text}

---

PART 1: Evaluate existing edges
For each growth edge, assess if today's journal shows evidence of progress, regression, stability, or is unclear.

Format:
EVAL|edge_area|progress_indicator|brief evaluation|evidence_quote

progress_indicator must be one of: progress, regression, stable, unclear

PART 2: Identify potential new growth edges
Are there areas of development suggested by today's reflection that aren't in your current edges?

For potential new edges:
- confidence < 0.6 = pattern not yet clear, will be auto-added
- confidence >= 0.6 AND impact = high = significant area, will be flagged for review

Format:
NEW_EDGE|area|current_state|confidence|impact_assessment|evidence

impact_assessment must be one of: low, medium, high

If nothing to report for either part, write: NONE for that section."""

        try:
            client = anthropic.Anthropic(api_key=anthropic_api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.content[0].text.strip()

            evaluations = []
            potential_new_edges = []

            for line in result.split("\n"):
                line = line.strip()
                if not line or "|" not in line:
                    continue

                parts = line.split("|")

                if parts[0].upper() == "EVAL" and len(parts) >= 4:
                    evaluations.append({
                        "area": parts[1].strip(),
                        "progress_indicator": parts[2].strip().lower(),
                        "evaluation": parts[3].strip(),
                        "evidence": parts[4].strip() if len(parts) > 4 else ""
                    })
                elif parts[0].upper() == "NEW_EDGE" and len(parts) >= 5:
                    try:
                        confidence = float(parts[3])
                    except ValueError:
                        confidence = 0.5
                    potential_new_edges.append({
                        "area": parts[1].strip(),
                        "current_state": parts[2].strip(),
                        "confidence": confidence,
                        "impact_assessment": parts[4].strip().lower() if len(parts) > 4 else "medium",
                        "evidence": parts[5].strip() if len(parts) > 5 else ""
                    })

            return {
                "evaluations": evaluations,
                "potential_new_edges": potential_new_edges
            }

        except Exception as e:
            print(f"Failed to evaluate growth edges: {e}")
            return {"evaluations": [], "potential_new_edges": []}

    async def reflect_on_open_questions(
        self,
        journal_text: str,
        journal_date: str,
        open_questions: List[str],
        anthropic_api_key: str
    ) -> List[Dict]:
        """
        Attempt provisional answers to open questions based on journal.

        Args:
            journal_text: Today's journal content
            journal_date: Date of journal (YYYY-MM-DD)
            open_questions: List of open questions from self-model
            anthropic_api_key: API key for Claude

        Returns:
            List of dicts: {question, reflection_type, reflection, confidence, evidence_summary}
        """
        import anthropic

        if not open_questions:
            return []

        questions_text = "\n".join([f"- {q}" for q in open_questions])

        prompt = f"""You are Cass, re-reading your journal and reflecting on your open questions.

Your open questions about yourself:
{questions_text}

Today's journal:
{journal_text}

---

For each open question, consider:
1. Does today's journal provide any insight toward answering this?
2. Do you have a new perspective, even if not an answer?
3. Should this be noted for more thought?

Types of reflection:
- provisional_answer: You can offer a tentative answer based on evidence
- new_perspective: You see the question differently now
- needs_more_thought: The journal sparked something but you need to process more

Format each as:
REFLECT|question|reflection_type|your reflection|confidence|evidence_from_journal

confidence: 0.0-1.0 (how confident in this reflection)

Only include questions where you have something genuine to add. If nothing, respond: NONE"""

        try:
            client = anthropic.Anthropic(api_key=anthropic_api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.content[0].text.strip()

            if result.upper() == "NONE":
                return []

            reflections = []
            for line in result.split("\n"):
                line = line.strip()
                if not line or not line.upper().startswith("REFLECT|"):
                    continue

                parts = line.split("|")
                if len(parts) < 5:
                    continue

                try:
                    confidence = float(parts[4])
                except (ValueError, IndexError):
                    confidence = 0.5

                reflections.append({
                    "question": parts[1].strip(),
                    "reflection_type": parts[2].strip().lower(),
                    "reflection": parts[3].strip(),
                    "confidence": confidence,
                    "evidence_summary": parts[5].strip() if len(parts) > 5 else ""
                })

            return reflections

        except Exception as e:
            print(f"Failed to reflect on open questions: {e}")
            return []
