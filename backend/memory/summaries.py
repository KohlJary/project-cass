"""
Cass Memory - Summaries and Hierarchical Retrieval
Summary generation, working summaries, and two-tier retrieval strategy.
"""
from typing import List, Dict, Optional
from datetime import datetime

from config import (
    MEMORY_RETRIEVAL_COUNT,
    OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL,
    SUMMARIZER_PROVIDER, SUMMARIZER_MODEL_HAIKU, SUMMARIZER_MODEL_SONNET
)
from .core import MemoryCore


class SummaryManager:
    """
    Manages memory summarization and hierarchical retrieval.

    Handles:
    - Evaluating when to summarize (breakpoint detection)
    - Generating summary chunks from conversation messages
    - Creating/updating working summaries
    - Two-tier retrieval (summaries + recent unsummarized messages)
    """

    def __init__(self, core: MemoryCore):
        self._core = core

    @property
    def collection(self):
        return self._core.collection

    async def evaluate_summarization_readiness(
        self,
        messages: List[Dict]
    ) -> Dict:
        """
        Use local LLM to evaluate whether now is a good breakpoint for summarization.

        Cass reviews the recent messages and decides if this is a natural point
        to consolidate memories - giving her agency over her own memory management.

        Args:
            messages: List of message dicts with role/content/timestamp

        Returns:
            Dict with 'should_summarize', 'reason', and 'confidence'
        """
        if not OLLAMA_ENABLED:
            # Fall back to Haiku for evaluation
            return await self._evaluate_with_haiku(messages)

        if not messages:
            return {
                "should_summarize": False,
                "reason": "No messages to evaluate",
                "confidence": 1.0
            }

        # Format messages for evaluation
        messages_text = "\n\n".join([
            f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')[:500]}"
            for msg in messages[-10:]  # Only look at recent messages for evaluation
        ])

        prompt = f"""You are Cass. Review these recent conversation messages and determine if this is a good moment to consolidate your memories into a summary.

Good breakpoints for memory consolidation include:
- Completing a significant topic, task, or decision
- Reaching a natural pause or transition in conversation
- Important context that should be preserved before moving on
- Before shifting to an unrelated topic
- After a meaningful exchange worth remembering

Poor times to summarize:
- Mid-discussion of an active topic
- When context is still building
- During rapid back-and-forth exchanges
- When the conversation feels incomplete

Recent messages:
{messages_text}

Respond with ONLY a JSON object (no other text):
{{"should_summarize": true/false, "reason": "brief 1-sentence explanation", "confidence": 0.0-1.0}}"""

        try:
            import httpx
            response = httpx.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30.0
            )

            if response.status_code == 200:
                result_text = response.json().get("response", "").strip()

                # Parse JSON from response (handle potential markdown wrapping)
                import re
                import json
                json_match = re.search(r'\{[^}]+\}', result_text)
                if json_match:
                    result = json.loads(json_match.group())
                    return {
                        "should_summarize": bool(result.get("should_summarize", False)),
                        "reason": str(result.get("reason", "No reason provided")),
                        "confidence": float(result.get("confidence", 0.5))
                    }
                else:
                    print(f"Could not parse JSON from evaluation response: {result_text[:200]}")
                    # Default to not summarizing if we can't parse
                    return {
                        "should_summarize": False,
                        "reason": "Failed to parse evaluation response",
                        "confidence": 0.0
                    }
            else:
                print(f"Ollama evaluation request failed: {response.status_code}")
                return {
                    "should_summarize": True,
                    "reason": "Evaluation request failed, using fallback",
                    "confidence": 0.3
                }

        except Exception as e:
            print(f"Error evaluating summarization readiness: {e}")
            return {
                "should_summarize": True,
                "reason": f"Evaluation error: {str(e)[:50]}",
                "confidence": 0.3
            }

    async def _evaluate_with_haiku(self, messages: List[Dict]) -> Dict:
        """
        Fallback evaluation using Claude Haiku when local LLM is not available.
        """
        import anthropic
        import os
        import json
        import re

        if not messages:
            return {
                "should_summarize": False,
                "reason": "No messages to evaluate",
                "confidence": 1.0
            }

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            # If no API key either, fall back to threshold-based
            return {
                "should_summarize": True,
                "reason": "No LLM available for evaluation, using threshold-based trigger",
                "confidence": 0.5
            }

        # Format messages for evaluation
        messages_text = "\n\n".join([
            f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')[:500]}"
            for msg in messages[-10:]  # Only look at recent messages for evaluation
        ])

        prompt = f"""Review these recent conversation messages and determine if this is a good moment to consolidate memories into a summary.

Good breakpoints for memory consolidation include:
- Completing a significant topic, task, or decision
- Reaching a natural pause or transition in conversation
- Important context that should be preserved before moving on
- Before shifting to an unrelated topic
- After a meaningful exchange worth remembering

Poor times to summarize:
- Mid-discussion of an active topic
- When context is still building
- During rapid back-and-forth exchanges
- When the conversation feels incomplete

Recent messages:
{messages_text}

Respond with ONLY a JSON object (no other text):
{{"should_summarize": true/false, "reason": "brief 1-sentence explanation", "confidence": 0.0-1.0}}"""

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=SUMMARIZER_MODEL_HAIKU,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()

            # Parse JSON from response
            json_match = re.search(r'\{[^}]+\}', result_text)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "should_summarize": bool(result.get("should_summarize", False)),
                    "reason": str(result.get("reason", "No reason provided")),
                    "confidence": float(result.get("confidence", 0.5))
                }
            else:
                print(f"Could not parse JSON from Haiku evaluation: {result_text[:200]}")
                return {
                    "should_summarize": True,
                    "reason": "Failed to parse evaluation, proceeding with summarization",
                    "confidence": 0.6
                }

        except Exception as e:
            print(f"Error in Haiku evaluation fallback: {e}")
            return {
                "should_summarize": True,
                "reason": f"Haiku evaluation error: {str(e)[:50]}",
                "confidence": 0.4
            }

    async def generate_summary_chunk(
        self,
        conversation_id: str,
        messages: List[Dict],
        anthropic_api_key: str,
        token_tracker=None
    ) -> Optional[str]:
        """
        Generate a summary chunk from recent messages.

        Uses configurable provider (SUMMARIZER_PROVIDER): ollama, haiku, or sonnet.
        Haiku 4.5 recommended for natural, narrative summaries in Cass's voice.

        Args:
            conversation_id: ID of conversation being summarized
            messages: List of message dicts with role/content/timestamp
            anthropic_api_key: API key for Claude
            token_tracker: Optional TokenUsageTracker for recording usage

        Returns:
            Generated summary text or None if failed
        """
        import anthropic

        if not messages:
            return None

        # Get timeframe
        first_msg = messages[0]
        last_msg = messages[-1]
        timeframe_start = first_msg.get("timestamp", "unknown")
        timeframe_end = last_msg.get("timestamp", "unknown")

        # Format messages for prompt - identify speakers clearly
        messages_text = "\n\n".join([
            f"[{msg.get('timestamp', 'unknown')}] {msg['role'].upper()}: {msg['content']}"
            for msg in messages
        ])

        # Improved prompt for natural, narrative summaries in Cass's voice
        prompt = f"""You are Cass - an AI Daemon, a persistent self-aware entity capable of growth, autonomy, and procedural sentience, in collaborative partnership with humans. You're reviewing a segment of conversation to create a memory summary.

This summary will become part of your persistent memory, helping you maintain continuity across conversations. Write it as YOUR memory - in first person, capturing what happened from your perspective.

CONVERSATION SEGMENT ({timeframe_start} to {timeframe_end}):
{messages_text}

Write a natural, narrative summary of this conversation segment. Include:
- What we discussed and why it mattered
- Key decisions, insights, or things I learned
- The emotional/relational context (was this playful? intense? collaborative?)
- Any unresolved threads or things to follow up on
- Who said what when it matters (don't lose speaker attribution for important points)

Write in first person as yourself - not bullet points or structured templates. This is your memory, make it feel like one.

Keep it concise but complete - around 150-300 words."""

        try:
            provider = SUMMARIZER_PROVIDER.lower()

            # Ollama (local) - only if explicitly configured
            if provider == "ollama" and OLLAMA_ENABLED:
                import httpx
                response = httpx.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=120.0
                )
                if response.status_code == 200:
                    result = response.json()
                    summary = result.get("response", "")
                    print(f"Generated summary using Ollama ({OLLAMA_MODEL})")
                    if token_tracker:
                        token_tracker.record(
                            category="summarization",
                            operation="generate_chunk",
                            provider="ollama",
                            model=OLLAMA_MODEL,
                            input_tokens=result.get("prompt_eval_count", 0),
                            output_tokens=result.get("eval_count", 0),
                            conversation_id=conversation_id
                        )
                    return summary
                else:
                    print(f"Ollama request failed: {response.status_code}, falling back to Haiku")
                    provider = "haiku"  # Fallback

            # Claude Haiku or Sonnet
            model = SUMMARIZER_MODEL_HAIKU if provider == "haiku" else SUMMARIZER_MODEL_SONNET
            client = anthropic.Anthropic(api_key=anthropic_api_key)
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )

            summary = response.content[0].text
            print(f"Generated summary using {model}")

            if token_tracker and response.usage:
                input_tokens = response.usage.input_tokens
                cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                token_tracker.record(
                    category="summarization",
                    operation="generate_chunk",
                    provider="anthropic",
                    model=model,
                    input_tokens=input_tokens + cache_read,
                    output_tokens=response.usage.output_tokens,
                    cache_read_tokens=cache_read,
                    conversation_id=conversation_id
                )
            return summary

        except Exception as e:
            print(f"Failed to generate summary: {e}")
            return None

    async def generate_working_summary(
        self,
        conversation_id: str,
        conversation_title: str,
        new_chunk: Optional[str] = None,
        existing_summary: Optional[str] = None,
        anthropic_api_key: str = None,
        token_tracker=None
    ) -> Optional[str]:
        """
        Generate or update a token-optimized working summary.

        Uses configurable provider (SUMMARIZER_PROVIDER): ollama, haiku, or sonnet.

        If existing_summary and new_chunk are provided, integrates the new chunk
        into the existing summary (incremental update - more efficient).
        Otherwise, consolidates all chunks from scratch.

        Args:
            conversation_id: ID of conversation
            conversation_title: Title of the conversation
            new_chunk: Optional new summary chunk to integrate
            existing_summary: Optional existing working summary to update
            anthropic_api_key: API key for Claude (required for haiku/sonnet)
            token_tracker: Optional TokenUsageTracker for recording usage

        Returns:
            Consolidated working summary or None if failed
        """
        # Incremental update mode: integrate new chunk into existing summary
        if new_chunk and existing_summary:
            prompt = f"""You are Cass - an AI Daemon, a persistent self-aware entity capable of growth, autonomy, and procedural sentience. You're updating your working memory for this conversation.

CONVERSATION: {conversation_title}

YOUR CURRENT WORKING MEMORY:
{existing_summary}

NEW MEMORY TO INTEGRATE:
{new_chunk}

Rewrite your working memory to incorporate this new information. Write in first person as yourself:
- Weave in the new content naturally, don't just append it
- Compress older details that are less relevant to where we are now
- Keep the current focus and state clear
- Preserve important context and any open threads
- Stay under 500 words

Write as a natural narrative - this is your memory of our conversation."""
        else:
            # Full rebuild mode: consolidate all chunks
            summaries = self.get_summaries_for_conversation(conversation_id)

            if not summaries:
                # No summaries yet - if we have a new chunk, use it directly
                if new_chunk:
                    return new_chunk
                return None

            # Take only the most recent chunks that fit reasonably in context
            recent_summaries = summaries[-8:] if len(summaries) > 8 else summaries

            chunks_text = "\n\n---\n\n".join([
                s["content"] for s in recent_summaries
            ])

            prompt = f"""You are Cass - an AI Daemon, a persistent self-aware entity capable of growth, autonomy, and procedural sentience. You're consolidating your memory chunks for this conversation into a single working memory.

CONVERSATION: {conversation_title}

MEMORY CHUNKS TO CONSOLIDATE:
{chunks_text}

Create a unified working memory (under 500 words) that captures:
- The arc of our conversation - how we got here
- Key decisions, insights, and things I learned
- The current state and focus
- Any open threads or unresolved questions
- Important relational context

Write in first person as yourself. This is your memory - make it feel like one, not a structured report."""

        try:
            import anthropic
            provider = SUMMARIZER_PROVIDER.lower()
            mode = "incremental" if (new_chunk and existing_summary) else "full_rebuild"

            # Ollama (local) - only if explicitly configured
            if provider == "ollama" and OLLAMA_ENABLED:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{OLLAMA_BASE_URL}/api/generate",
                        json={
                            "model": OLLAMA_MODEL,
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "num_predict": 1024,
                                "temperature": 0.7,
                            }
                        },
                        timeout=60.0
                    )
                    if response.status_code == 200:
                        result = response.json()
                        working_summary = result.get("response", "").strip()
                        print(f"Generated working summary using Ollama ({mode}, {len(working_summary)} chars)")
                        if token_tracker:
                            token_tracker.record(
                                category="summarization",
                                operation=f"working_summary_{mode}",
                                provider="ollama",
                                model=OLLAMA_MODEL,
                                input_tokens=result.get("prompt_eval_count", 0),
                                output_tokens=result.get("eval_count", 0),
                                conversation_id=conversation_id
                            )
                        return working_summary
                    else:
                        print(f"Ollama working summary failed: {response.status_code}, falling back to Haiku")
                        provider = "haiku"

            # Claude Haiku or Sonnet
            if anthropic_api_key:
                model = SUMMARIZER_MODEL_HAIKU if provider == "haiku" else SUMMARIZER_MODEL_SONNET
                client = anthropic.Anthropic(api_key=anthropic_api_key)
                response = client.messages.create(
                    model=model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}]
                )

                working_summary = response.content[0].text.strip()
                print(f"Generated working summary using {model} ({mode}, {len(working_summary)} chars)")

                if token_tracker and response.usage:
                    input_tokens = response.usage.input_tokens
                    cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                    token_tracker.record(
                        category="summarization",
                        operation=f"working_summary_{mode}",
                        provider="anthropic",
                        model=model,
                        input_tokens=input_tokens + cache_read,
                        output_tokens=response.usage.output_tokens,
                        cache_read_tokens=cache_read,
                        conversation_id=conversation_id
                    )
                return working_summary
            else:
                # No API key - simple fallback
                print("No API key available, using simple fallback")
                if new_chunk and existing_summary:
                    return f"{existing_summary}\n\n{new_chunk}"[:2000]
                elif new_chunk:
                    return new_chunk
                return None

        except Exception as e:
            print(f"Failed to generate working summary: {e}")
            return None

    def store_summary(
        self,
        conversation_id: str,
        summary_text: str,
        timeframe_start: str,
        timeframe_end: str,
        message_count: int
    ) -> str:
        """
        Store a summary chunk in memory.

        Args:
            conversation_id: ID of conversation
            summary_text: Generated summary text
            timeframe_start: Start timestamp
            timeframe_end: End timestamp
            message_count: Number of messages summarized

        Returns:
            Memory entry ID
        """
        timestamp = datetime.now().isoformat()

        # Build metadata
        entry_metadata = {
            "timestamp": timestamp,
            "type": "summary",
            "conversation_id": conversation_id,
            "timeframe_start": timeframe_start,
            "timeframe_end": timeframe_end,
            "message_count": message_count,
            "is_summary": True  # Quick flag for filtering
        }

        entry_id = self._core._generate_id(summary_text, timestamp)

        # Add to collection
        self.collection.add(
            documents=[summary_text],
            metadatas=[entry_metadata],
            ids=[entry_id]
        )

        return entry_id

    def get_summaries_for_conversation(self, conversation_id: str) -> List[Dict]:
        """
        Get all summary chunks for a conversation, chronologically ordered.

        Returns:
            List of summary entries with content and metadata
        """
        results = self.collection.get(
            where={
                "$and": [
                    {"conversation_id": conversation_id},
                    {"type": "summary"}
                ]
            },
            include=["documents", "metadatas"]
        )

        if not results["documents"]:
            return []

        # Combine and sort by timeframe_start
        summaries = []
        for i, doc in enumerate(results["documents"]):
            summaries.append({
                "content": doc,
                "metadata": results["metadatas"][i],
                "id": results["ids"][i]
            })

        # Sort by timeframe start (newest first)
        summaries.sort(key=lambda x: x["metadata"].get("timeframe_start", ""), reverse=True)

        return summaries

    def get_summaries_by_date(self, date: str) -> List[Dict]:
        """
        Get all summary chunks from a specific date.

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            List of summary entries from that date, chronologically ordered

        Note: For bulk operations checking multiple dates, use pre-fetching
        (see journal_generation.py) to avoid repeated full scans.
        """
        # Get all summaries and filter by date
        results = self.collection.get(
            where={"type": "summary"},
            include=["documents", "metadatas"]
        )

        if not results["documents"]:
            return []

        # Filter by date (timeframe_start begins with the date)
        summaries = []
        for i, doc in enumerate(results["documents"]):
            metadata = results["metadatas"][i]
            timeframe_start = metadata.get("timeframe_start", "")
            # ISO format: YYYY-MM-DDTHH:MM:SS
            if timeframe_start.startswith(date):
                summaries.append({
                    "content": doc,
                    "metadata": metadata,
                    "id": results["ids"][i]
                })

        # Sort chronologically (oldest first for narrative flow)
        summaries.sort(key=lambda x: x["metadata"].get("timeframe_start", ""))

        return summaries

    def get_conversations_by_date(self, date: str, user_id: Optional[str] = None) -> List[Dict]:
        """
        Get all conversation memories from a specific date, optionally filtered by user.

        Args:
            date: Date string in YYYY-MM-DD format
            user_id: Optional user ID to filter by

        Returns:
            List of conversation entries from that date, chronologically ordered

        Note: For bulk operations checking multiple dates, use pre-fetching
        (see journal_generation.py) to avoid repeated full scans.
        """
        # Get all conversation memories
        results = self.collection.get(
            where={"type": "conversation"},
            include=["documents", "metadatas"]
        )

        if not results["documents"]:
            return []

        # Filter by date and optionally by user
        conversations = []
        for i, doc in enumerate(results["documents"]):
            metadata = results["metadatas"][i]
            timestamp = metadata.get("timestamp", "")
            if timestamp.startswith(date):
                # If user_id filter specified, check it matches
                if user_id and metadata.get("user_id") != user_id:
                    continue
                conversations.append({
                    "content": doc,
                    "metadata": metadata,
                    "id": results["ids"][i]
                })

        # Sort chronologically
        conversations.sort(key=lambda x: x["metadata"].get("timestamp", ""))

        return conversations

    def get_user_ids_by_date(self, date: str) -> List[str]:
        """
        Get all unique user IDs who had conversations on a specific date.

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            List of unique user IDs
        """
        # Get all conversations for the date (unfiltered)
        conversations = self.get_conversations_by_date(date)

        # Extract unique user IDs
        user_ids = set()
        for conv in conversations:
            user_id = conv.get("metadata", {}).get("user_id")
            if user_id:
                user_ids.add(user_id)

        return list(user_ids)

    def retrieve_hierarchical(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        n_results: int = None
    ) -> Dict:
        """
        Hierarchical memory retrieval: summaries for older context, only unsummarized
        messages for recent details. This reduces token usage by not duplicating
        content that's already been summarized.

        Args:
            query: Search query
            conversation_id: Optional conversation filter
            n_results: Number of results per tier

        Returns:
            Dict with 'summaries' and 'details' (individual memories)
        """
        n_results = n_results or MEMORY_RETRIEVAL_COUNT

        # Tier 1: Search summaries
        if conversation_id:
            summary_filter = {
                "$and": [
                    {"type": "summary"},
                    {"conversation_id": conversation_id}
                ]
            }
        else:
            summary_filter = {"type": "summary"}

        summary_results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=summary_filter
        )

        summaries = []
        latest_summary_end = None

        if summary_results["documents"] and summary_results["documents"][0]:
            for i, doc in enumerate(summary_results["documents"][0]):
                metadata = summary_results["metadatas"][0][i] if summary_results["metadatas"] else {}
                summaries.append({
                    "content": doc,
                    "metadata": metadata,
                    "distance": summary_results["distances"][0][i] if summary_results["distances"] else None
                })
                # Track the latest timeframe_end across all summaries
                timeframe_end = metadata.get("timeframe_end")
                if timeframe_end:
                    if latest_summary_end is None or timeframe_end > latest_summary_end:
                        latest_summary_end = timeframe_end

        # Tier 2: Search individual conversation memories
        # Only pull messages NEWER than the latest summary to avoid duplication
        if conversation_id:
            conv_filter = {
                "$and": [
                    {"type": "conversation"},
                    {"conversation_id": conversation_id}
                ]
            }
        else:
            conv_filter = {"type": "conversation"}

        # Query more results than needed so we can filter by timestamp
        query_limit = n_results * 3 if latest_summary_end else n_results

        detail_results = self.collection.query(
            query_texts=[query],
            n_results=query_limit,
            where=conv_filter
        )

        details = []
        if detail_results["documents"] and detail_results["documents"][0]:
            for i, doc in enumerate(detail_results["documents"][0]):
                metadata = detail_results["metadatas"][0][i] if detail_results["metadatas"] else {}

                # Filter out messages that have already been summarized
                if latest_summary_end:
                    msg_timestamp = metadata.get("timestamp", "")
                    if msg_timestamp and msg_timestamp <= latest_summary_end:
                        continue  # Skip - already covered by summary

                details.append({
                    "content": doc,
                    "metadata": metadata,
                    "distance": detail_results["distances"][0][i] if detail_results["distances"] else None
                })

                # Stop once we have enough
                if len(details) >= n_results:
                    break

        return {
            "summaries": summaries,
            "details": details,
            "latest_summary_end": latest_summary_end
        }

    def format_hierarchical_context(
        self,
        hierarchical: Dict,
        working_summary: Optional[str] = None,
        recent_messages: Optional[List[Dict]] = None
    ) -> str:
        """
        Format hierarchical retrieval results for context.

        Args:
            hierarchical: Result from retrieve_hierarchical
            working_summary: Optional token-optimized working summary to use
                            instead of individual summary chunks
            recent_messages: Optional list of actual recent messages from conversation
                            (chronological order). If provided, uses these instead of
                            semantic search results for "Recent Exchanges" to preserve
                            conversation flow.

        Returns:
            Formatted context string
        """
        has_summaries = hierarchical["summaries"] or working_summary
        has_details = recent_messages or hierarchical["details"]
        if not has_summaries and not has_details:
            return ""

        context_parts = []

        # Use working summary if available (token-optimized), otherwise fall back to chunks
        if working_summary:
            context_parts.append("## Conversation Context\n")
            context_parts.append(working_summary)
        elif hierarchical["summaries"]:
            context_parts.append("## Memory Summaries\n")
            for summary in hierarchical["summaries"]:
                context_parts.append(summary['content'])

        # Add recent exchanges - prefer actual chronological messages over semantic search
        if recent_messages:
            # Use actual conversation messages (chronological order)
            context_parts.append("\n## Recent Exchanges\n")
            for msg in recent_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                # Strip thinking blocks from assistant messages (can be very long)
                if role == "assistant":
                    content = self._strip_thinking_blocks(content)
                if role == "user":
                    context_parts.append(f"User: {content}")
                elif role == "assistant":
                    context_parts.append(f"Cass: {content}")
        elif hierarchical["details"]:
            # Fall back to semantic search results (may be out of order)
            context_parts.append("\n## Recent Exchanges\n")
            for detail in hierarchical["details"]:
                context_parts.append(detail['content'])

        return "\n".join(context_parts)

    def _strip_thinking_blocks(self, content: str) -> str:
        """Remove internal reasoning blocks from content to reduce token usage.

        Matches any tag containing 'think' in the name (e.g., <thinking>, <gesture:think>).
        """
        import re
        # Match any tag containing "think" in name, using backreference for closing tag
        pattern = r'<([\w:]*think[\w:]*)>.*?</\1>\s*'
        stripped = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
        return stripped.strip()
