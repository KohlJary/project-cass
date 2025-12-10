"""Extracted from main_sdk.py"""


from handlers import execute_journal_tool, execute_calendar_tool, execute_task_tool, execute_document_tool, execute_self_model_tool, execute_user_model_tool, execute_roadmap_tool, execute_wiki_tool, execute_testing_tool, execute_research_tool, execute_solo_reflection_tool, execute_insight_tool, execute_goal_tool, execute_web_research_tool, execute_research_session_tool, execute_research_scheduler_tool
from typing import Optional, List, Dict
import re
import logging

logger = logging.getLogger(__name__)

# These will be injected by main_sdk.py after import
wiki_retrieval = None
_wiki_context_cache: Dict[str, tuple] = {}
_WIKI_CACHE_TTL_SECONDS = 300  # 5 minutes

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
) -> str:
    """
    Process inline XML tags in response text, execute corresponding tool calls,
    and strip the tags from the output.

    Handles:
    - <record_self_observation> tags
    - <record_user_observation> tags
    - <create_roadmap_item> tags

    Returns:
        Cleaned text with tags stripped
    """
    cleaned_text = text

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

    # Strip all inline tags from the text
    cleaned_text = INLINE_SELF_OBSERVATION_PATTERN.sub('', cleaned_text)
    cleaned_text = INLINE_USER_OBSERVATION_PATTERN.sub('', cleaned_text)
    cleaned_text = INLINE_ROADMAP_ITEM_PATTERN.sub('', cleaned_text)

    # Clean up extra whitespace
    cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

    return cleaned_text
