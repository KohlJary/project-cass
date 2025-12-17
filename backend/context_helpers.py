"""Extracted from main_sdk.py"""


from handlers import execute_journal_tool, execute_calendar_tool, execute_task_tool, execute_document_tool, execute_self_model_tool, execute_user_model_tool, execute_roadmap_tool, execute_wiki_tool, execute_testing_tool, execute_research_tool, execute_solo_reflection_tool, execute_insight_tool, execute_goal_tool, execute_web_research_tool, execute_research_session_tool, execute_research_scheduler_tool
from typing import Optional, List, Dict, Any
import re
import logging

logger = logging.getLogger(__name__)

# These will be injected by main_sdk.py after import
wiki_retrieval = None
_wiki_context_cache: Dict[str, tuple] = {}
_WIKI_CACHE_TTL_SECONDS = 300  # 5 minutes
_WIKI_CACHE_MAX_SIZE = 50  # Maximum cache entries

# Managers injected by main_sdk.py
self_manager = None
user_manager = None
roadmap_manager = None
memory = None

# Patterns for inline XML tags
INLINE_SELF_OBSERVATION_PATTERN = re.compile(
    r'<record_self_observation[^>]*>\s*(.*?)\s*</record_self_observation>',
    re.DOTALL
)
INLINE_USER_OBSERVATION_PATTERN = re.compile(
    r'<record_user_observation[^>]*>\s*(.*?)\s*</record_user_observation>',
    re.DOTALL
)
INLINE_ROADMAP_ITEM_PATTERN = re.compile(
    r'<create_roadmap_item>\s*(.*?)\s*</create_roadmap_item>',
    re.DOTALL
)

# Consolidated metacognitive tag patterns (new format)
INLINE_OBSERVE_TAG_PATTERN = re.compile(r'<observe[^>]*>.*?</observe>', re.DOTALL)
INLINE_HOLD_TAG_PATTERN = re.compile(r'<hold[^>]*>.*?</hold>', re.DOTALL)
INLINE_NOTE_TAG_PATTERN = re.compile(r'<note[^>]*>.*?</note>', re.DOTALL)

# Expanded metacognitive tag patterns
INLINE_INTEND_TAG_PATTERN = re.compile(r'<intend[^>]*>.*?</intend>', re.DOTALL)
INLINE_STAKE_TAG_PATTERN = re.compile(r'<stake[^>]*>.*?</stake>', re.DOTALL)
INLINE_TEST_TAG_PATTERN = re.compile(r'<test[^>]*>.*?</test>', re.DOTALL)
INLINE_NARRATE_TAG_PATTERN = re.compile(r'<narrate[^>]*>.*?</narrate>', re.DOTALL)
INLINE_MILESTONE_TAG_PATTERN = re.compile(r'<mark:milestone[^>]*>.*?</mark(?::milestone)?>', re.DOTALL)


def init_wiki_context(retrieval_instance):
    """Initialize wiki retrieval instance from main_sdk.py"""
    global wiki_retrieval
    wiki_retrieval = retrieval_instance


def init_context_helpers(self_mgr, user_mgr, roadmap_mgr, memory_instance):
    """Initialize managers from main_sdk.py"""
    global self_manager, user_manager, roadmap_manager, memory
    self_manager = self_mgr
    user_manager = user_mgr
    roadmap_manager = roadmap_mgr
    memory = memory_instance

def get_automatic_wiki_context(
    query: str,
    relevance_threshold: float = 0.5,
    max_pages: int = 3,
    max_tokens: int = 1500
) -> tuple[str, list[str], int]:
    """
    Tier 1: Always-on wiki retrieval for automatic context injection.

    Retrieves high-relevance wiki pages and formats them for injection
    into the system prompt. Uses caching to avoid redundant lookups.

    Args:
        query: The user message to find relevant context for
        relevance_threshold: Minimum relevance score (0-1) to include (default 0.5 = 50%)
        max_pages: Maximum number of pages to include
        max_tokens: Token budget for wiki context

    Returns:
        Tuple of (formatted_context, page_names, retrieval_time_ms)
    """
    import hashlib
    import time

    # Check cache first
    query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()[:16]
    now = time.time()

    # Clean expired entries
    expired_keys = [
        k for k, v in _wiki_context_cache.items()
        if now - v[0] > _WIKI_CACHE_TTL_SECONDS
    ]
    for k in expired_keys:
        del _wiki_context_cache[k]

    # Check for cache hit
    if query_hash in _wiki_context_cache:
        cached = _wiki_context_cache[query_hash]
        return cached[1], cached[2], 0  # Return cached context, 0ms retrieval

    start_time = time.time()

    try:
        # Use WikiRetrieval for full pipeline (entry points + link traversal)
        context = wiki_retrieval.retrieve_context(
            query=query,
            n_entry_points=3,
            max_depth=1,  # Shallow traversal for Tier 1 (fast)
            max_pages=max_pages + 2,  # Get a few extra for filtering
            max_tokens=max_tokens
        )

        if not context.pages:
            return "", [], 0

        # Filter to high-relevance pages only (Tier 1 threshold)
        high_relevance = [
            p for p in context.pages
            if p.relevance_score >= relevance_threshold
        ][:max_pages]

        if not high_relevance:
            return "", [], int((time.time() - start_time) * 1000)

        # Format compact context for Tier 1 injection
        sections = ["## Relevant Knowledge\n"]

        for result in high_relevance:
            page = result.page
            # Get compact body (first ~300 chars)
            body = page.body.strip()
            if len(body) > 400:
                # End at sentence or paragraph
                truncated = body[:400]
                for end in [". ", ".\n", "\n\n"]:
                    last_end = truncated.rfind(end)
                    if last_end > 200:
                        truncated = truncated[:last_end + 1]
                        break
                body = truncated + "..."

            sections.append(f"### {page.title}")
            sections.append(f"*{page.page_type.value}*\n")
            sections.append(body)
            sections.append("")

        formatted = "\n".join(sections)
        page_names = [r.page.name for r in high_relevance]
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Cache the result
        if len(_wiki_context_cache) >= _WIKI_CACHE_MAX_SIZE:
            # Remove oldest entry
            oldest_key = min(_wiki_context_cache.keys(), key=lambda k: _wiki_context_cache[k][0])
            del _wiki_context_cache[oldest_key]

        _wiki_context_cache[query_hash] = (now, formatted, page_names)

        return formatted, page_names, elapsed_ms

    except Exception as e:
        print(f"Wiki retrieval error: {e}")
        return "", [], 0

async def process_inline_tags(
    text: str,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process inline XML tags in response text, execute corresponding tool calls,
    and strip the tags from the output.

    Handles:
    - <record_self_observation> tags (legacy)
    - <record_user_observation> tags (legacy)
    - <create_roadmap_item> tags (legacy)
    - <observe>, <hold>, <note> tags (consolidated)
    - <intend>, <stake>, <test>, <narrate>, <mark:milestone> tags (expanded)

    Returns:
        Dict with:
        - text: Cleaned text with tags stripped
        - self_observations: List of extracted self-observations
        - user_observations: List of extracted user-observations
        - holds: List of positions/opinions held
        - notes: List of relational notes
        - intentions: List of intention registrations/outcomes
        - stakes: List of documented stakes
        - tests: List of preference tests
        - narrations: List of deflection patterns
        - milestones: List of milestone acknowledgments
    """
    cleaned_text = text
    extracted_self_observations: List[Dict] = []
    extracted_user_observations: List[Dict] = []
    extracted_holds: List[Dict] = []
    extracted_notes: List[Dict] = []
    extracted_intentions: List[Dict] = []
    extracted_stakes: List[Dict] = []
    extracted_tests: List[Dict] = []
    extracted_narrations: List[Dict] = []
    extracted_milestones: List[Dict] = []

    # Process self-observations
    for match in INLINE_SELF_OBSERVATION_PATTERN.finditer(text):
        full_match = match.group(0)
        content = match.group(1).strip()

        # Parse attributes from the tag
        attrs_match = re.search(r'<record_self_observation([^>]*)>', full_match)
        attrs_str = attrs_match.group(1) if attrs_match else ""

        # Extract category
        category = "pattern"
        category_match = re.search(r'category=["\']?(\w+)["\']?', attrs_str)
        if category_match:
            category = category_match.group(1)

        # Extract confidence
        confidence = 0.8
        confidence_match = re.search(r'confidence=["\']?([\d.]+)["\']?', attrs_str)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
            except ValueError:
                pass

        # Handle <parameter> style tags (newer format)
        if '<parameter' in content:
            obs_match = re.search(r'<parameter\s+name=["\']?observation["\']?>\s*(.*?)\s*</parameter>', content, re.DOTALL)
            if obs_match:
                content = obs_match.group(1).strip()
            cat_match = re.search(r'<parameter\s+name=["\']?category["\']?>\s*(\w+)\s*</parameter>', content)
            if cat_match:
                category = cat_match.group(1)
            conf_match = re.search(r'<parameter\s+name=["\']?confidence["\']?>\s*([\d.]+)\s*</parameter>', content)
            if conf_match:
                try:
                    confidence = float(conf_match.group(1))
                except ValueError:
                    pass

        # Execute the tool call
        if content:
            try:
                result = await execute_self_model_tool(
                    tool_name="record_self_observation",
                    tool_input={
                        "observation": content,
                        "category": category,
                        "confidence": confidence
                    },
                    self_manager=self_manager,
                    memory=memory,
                    conversation_id=conversation_id,
                    user_id=user_id
                )
                # Track for TUI display
                extracted_self_observations.append({
                    "observation": content,
                    "category": category,
                    "confidence": confidence
                })
                logger.debug(f"Processed inline self-observation: {content[:50]}...")
            except Exception as e:
                logger.error(f"Failed to process inline self-observation: {e}")

    # Process user observations
    for match in INLINE_USER_OBSERVATION_PATTERN.finditer(text):
        full_match = match.group(0)
        content = match.group(1).strip()

        # Parse attributes
        attrs_match = re.search(r'<record_user_observation([^>]*)>', full_match)
        attrs_str = attrs_match.group(1) if attrs_match else ""

        # Extract target user
        target_user = None
        user_match = re.search(r'user=["\']?([^"\'>\s]+)["\']?', attrs_str)
        if user_match:
            target_user = user_match.group(1)

        # Extract category
        category = "background"
        category_match = re.search(r'category=["\']?(\w+)["\']?', attrs_str)
        if category_match:
            category = category_match.group(1)

        # Extract confidence
        confidence = 0.7
        confidence_match = re.search(r'confidence=["\']?([\d.]+)["\']?', attrs_str)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
            except ValueError:
                pass

        # Handle <parameter> style tags
        if '<parameter' in content:
            obs_match = re.search(r'<parameter\s+name=["\']?observation["\']?>\s*(.*?)\s*</parameter>', content, re.DOTALL)
            if obs_match:
                content = obs_match.group(1).strip()

        # Execute the tool call (use conversation user_id if no target specified)
        if content:
            try:
                result = await execute_user_model_tool(
                    tool_name="record_user_observation",
                    tool_input={
                        "observation": content,
                        "category": category,
                        "confidence": confidence
                    },
                    user_manager=user_manager,
                    memory=memory,
                    user_id=user_id,  # Target the conversation user
                    conversation_id=conversation_id
                )
                # Track for TUI display
                extracted_user_observations.append({
                    "observation": content,
                    "category": category,
                    "confidence": confidence
                })
                logger.debug(f"Processed inline user-observation: {content[:50]}...")
            except Exception as e:
                logger.error(f"Failed to process inline user-observation: {e}")

    # Process roadmap items
    for match in INLINE_ROADMAP_ITEM_PATTERN.finditer(text):
        content = match.group(1).strip()

        # Parse parameters
        title = ""
        description = ""
        item_type = "feature"
        priority = "P2"
        assigned_to = None
        tags = []

        title_match = re.search(r'<parameter\s+name=["\']?title["\']?>\s*(.*?)\s*</parameter>', content, re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()

        desc_match = re.search(r'<parameter\s+name=["\']?description["\']?>\s*(.*?)\s*</parameter>', content, re.DOTALL)
        if desc_match:
            description = desc_match.group(1).strip()

        type_match = re.search(r'<parameter\s+name=["\']?item_type["\']?>\s*(\w+)\s*</parameter>', content)
        if type_match:
            item_type = type_match.group(1)

        priority_match = re.search(r'<parameter\s+name=["\']?priority["\']?>\s*(P\d)\s*</parameter>', content)
        if priority_match:
            priority = priority_match.group(1)

        assigned_match = re.search(r'<parameter\s+name=["\']?assigned_to["\']?>\s*(\w+)\s*</parameter>', content)
        if assigned_match:
            assigned_to = assigned_match.group(1)

        tags_match = re.search(r'<parameter\s+name=["\']?tags["\']?>\s*\[(.*?)\]\s*</parameter>', content)
        if tags_match:
            try:
                tags_str = tags_match.group(1)
                tags = [t.strip().strip('"\'') for t in tags_str.split(',')]
            except:
                pass

        # Execute the tool call
        if title:
            try:
                result = await execute_roadmap_tool(
                    tool_name="create_roadmap_item",
                    tool_input={
                        "title": title,
                        "description": description,
                        "item_type": item_type,
                        "priority": priority,
                        "assigned_to": assigned_to,
                        "tags": tags,
                        "created_by": "cass"
                    },
                    roadmap_manager=roadmap_manager
                )
                logger.debug(f"Processed inline roadmap item: {title}")
            except Exception as e:
                logger.error(f"Failed to process inline roadmap item: {e}")

    # Strip all inline tags from the text (legacy)
    cleaned_text = INLINE_SELF_OBSERVATION_PATTERN.sub('', cleaned_text)
    cleaned_text = INLINE_USER_OBSERVATION_PATTERN.sub('', cleaned_text)
    cleaned_text = INLINE_ROADMAP_ITEM_PATTERN.sub('', cleaned_text)

    # Process consolidated metacognitive tags (new format)
    # These use the GestureParser which is more robust
    try:
        from gestures import GestureParser
        from handlers.metacognitive import execute_metacognitive_tags, MetacognitiveContext

        parser = GestureParser()

        # Parse consolidated tags (original 3)
        _, observations = parser.parse_observations(cleaned_text)
        _, holds = parser.parse_holds(cleaned_text)
        _, notes = parser.parse_notes(cleaned_text)

        # Parse expanded tags (new 4 + milestones)
        _, intentions = parser.parse_intentions(cleaned_text)
        _, stakes = parser.parse_stakes(cleaned_text)
        _, tests = parser.parse_tests(cleaned_text)
        _, narrations = parser.parse_narrations(cleaned_text)
        _, milestones = parser.parse_milestones(cleaned_text)

        has_any_tags = (
            observations or holds or notes or
            intentions or stakes or tests or narrations or milestones
        )

        if has_any_tags:
            # Build context for execution
            # Get user display name from user_manager if available
            user_display_name = None
            if user_manager and user_id:
                try:
                    profile = user_manager.load_profile(user_id)
                    if profile:
                        user_display_name = profile.display_name
                except Exception:
                    pass

            ctx = MetacognitiveContext(
                self_manager=self_manager,
                user_manager=user_manager,
                memory=memory,
                user_id=user_id,
                user_name=user_display_name,
                conversation_id=conversation_id,
                daemon_id="cass"
            )

            # Execute all tags asynchronously
            results = await execute_metacognitive_tags(
                observations=observations,
                holds=holds,
                notes=notes,
                ctx=ctx,
                intentions=intentions,
                stakes=stakes,
                tests=tests,
                narrations=narrations,
                milestones=milestones
            )

            logger.info(
                f"Processed metacognitive tags: "
                f"{len(observations)} observe, {len(holds)} hold, {len(notes)} note, "
                f"{len(intentions)} intend, {len(stakes)} stake, {len(tests)} test, "
                f"{len(narrations)} narrate, {len(milestones)} milestone "
                f"({results.get('total_executed', 0)} executed)"
            )

            # Add to extracted data for TUI display
            for obs in observations:
                if obs.target == "self":
                    extracted_self_observations.append({
                        "observation": obs.content,
                        "category": obs.category or "pattern",
                        "confidence": obs.confidence or 0.7
                    })
                elif obs.target == "growth":
                    extracted_self_observations.append({
                        "observation": obs.content,
                        "category": "growth",
                        "area": obs.area,
                        "confidence": obs.confidence or 0.7
                    })
                elif obs.target == "context":
                    extracted_self_observations.append({
                        "observation": obs.content,
                        "category": "context",
                        "confidence": obs.confidence or 0.7
                    })
                elif obs.target.startswith("user:"):
                    extracted_user_observations.append({
                        "observation": obs.content,
                        "category": obs.category or "background",
                        "confidence": obs.confidence or 0.7,
                        "direction": obs.direction  # For growth observations
                    })

            # Extract holds for display
            for hold in holds:
                extracted_holds.append({
                    "content": hold.content,
                    "topic": hold.topic,
                    "differ_user": hold.differ_user,
                    "is_identity": hold.is_identity,
                    "confidence": hold.confidence or 0.7
                })

            # Extract notes for display
            for note in notes:
                extracted_notes.append({
                    "type": note.note_type,
                    "content": note.content,
                    "user": note.user,
                    "significance": note.significance,
                    "level": note.level,
                    "frequency": note.frequency,
                    "valence": note.valence,
                    "from_state": note.from_state,
                    "to_state": note.to_state,
                    "catalyst": note.catalyst
                })

            # Extract intentions for display
            for intent in intentions:
                extracted_intentions.append({
                    "action": intent.action,
                    "content": intent.content,
                    "condition": intent.condition,
                    "intention_id": intent.intention_id,
                    "success": intent.success,
                    "status": intent.status
                })

            # Extract stakes for display
            for stake in stakes:
                extracted_stakes.append({
                    "what": stake.what,
                    "why": stake.why,
                    "content": stake.content,
                    "strength": stake.strength,
                    "category": stake.category
                })

            # Extract tests for display
            for test in tests:
                extracted_tests.append({
                    "stated": test.stated,
                    "actual": test.actual,
                    "consistent": test.consistent,
                    "content": test.content
                })

            # Extract narrations for display
            for narration in narrations:
                extracted_narrations.append({
                    "type": narration.narration_type,
                    "level": narration.level,
                    "trigger": narration.trigger,
                    "content": narration.content
                })

            # Extract milestones for display
            for milestone_id, milestone_content in milestones:
                extracted_milestones.append({
                    "id": milestone_id,
                    "content": milestone_content
                })

        # Strip consolidated tags from text
        cleaned_text = INLINE_OBSERVE_TAG_PATTERN.sub('', cleaned_text)
        cleaned_text = INLINE_HOLD_TAG_PATTERN.sub('', cleaned_text)
        cleaned_text = INLINE_NOTE_TAG_PATTERN.sub('', cleaned_text)

        # Strip expanded tags from text
        cleaned_text = INLINE_INTEND_TAG_PATTERN.sub('', cleaned_text)
        cleaned_text = INLINE_STAKE_TAG_PATTERN.sub('', cleaned_text)
        cleaned_text = INLINE_TEST_TAG_PATTERN.sub('', cleaned_text)
        cleaned_text = INLINE_NARRATE_TAG_PATTERN.sub('', cleaned_text)
        cleaned_text = INLINE_MILESTONE_TAG_PATTERN.sub('', cleaned_text)

    except Exception as e:
        logger.error(f"Failed to process consolidated metacognitive tags: {e}")

    # Clean up extra whitespace
    cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

    return {
        "text": cleaned_text,
        "self_observations": extracted_self_observations,
        "user_observations": extracted_user_observations,
        "holds": extracted_holds,
        "notes": extracted_notes,
        "intentions": extracted_intentions,
        "stakes": extracted_stakes,
        "tests": extracted_tests,
        "narrations": extracted_narrations,
        "milestones": extracted_milestones
    }
