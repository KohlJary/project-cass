"""
Wiki Updater - Background process to update wiki after conversations.

Analyzes conversation content to:
- Identify new entities/concepts to create pages for
- Update existing pages with new understanding
- Create/strengthen links between related pages
- Note uncertainties as open questions

This runs asynchronously after conversations, not blocking the chat flow.
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from datetime import datetime
import re

from .storage import WikiStorage, WikiPage, PageType


@dataclass
class WikiUpdateSuggestion:
    """A suggested wiki update from conversation analysis."""
    action: str  # "create", "update", "link"
    page_name: str
    page_type: Optional[PageType] = None
    content: Optional[str] = None
    target_page: Optional[str] = None  # For link actions
    reason: str = ""
    confidence: float = 0.5  # 0-1, how confident we are this is worthwhile


@dataclass
class ConversationAnalysis:
    """Results of analyzing a conversation for wiki updates."""
    suggestions: List[WikiUpdateSuggestion] = field(default_factory=list)
    entities_mentioned: Set[str] = field(default_factory=set)
    concepts_mentioned: Set[str] = field(default_factory=set)
    existing_pages_referenced: Set[str] = field(default_factory=set)
    analysis_time_ms: float = 0


class WikiUpdater:
    """
    Analyzes conversations and suggests/applies wiki updates.

    Can operate in two modes:
    1. Suggestion mode: Returns suggestions for human/Cass review
    2. Auto-apply mode: Automatically applies high-confidence updates
    """

    def __init__(
        self,
        wiki_storage: WikiStorage,
        memory=None,
        auto_apply_threshold: float = 0.8
    ):
        """
        Initialize the wiki updater.

        Args:
            wiki_storage: WikiStorage instance
            memory: CassMemory instance for embeddings
            auto_apply_threshold: Confidence threshold for auto-applying updates
        """
        self.wiki = wiki_storage
        self.memory = memory
        self.auto_apply_threshold = auto_apply_threshold

        # Patterns for entity extraction
        self.entity_patterns = [
            # Names (capitalized words)
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',
        ]

        # Words that indicate concepts worth tracking
        self.concept_indicators = [
            "believes", "thinks", "feels", "values", "wants",
            "learned", "discovered", "realized", "understands",
            "pattern", "approach", "method", "technique",
            "important", "significant", "key", "core",
        ]

    def analyze_conversation(
        self,
        messages: List[Dict],
        existing_context: Optional[str] = None
    ) -> ConversationAnalysis:
        """
        Analyze a conversation for potential wiki updates.

        Args:
            messages: List of message dicts with 'role' and 'content'
            existing_context: Optional wiki context that was used in the conversation

        Returns:
            ConversationAnalysis with suggestions
        """
        import time
        start_time = time.time()

        analysis = ConversationAnalysis()

        # Combine all message content
        full_text = "\n".join(
            msg.get("content", "") for msg in messages
            if msg.get("content")
        )

        # Extract entities and concepts
        analysis.entities_mentioned = self._extract_entities(full_text)
        analysis.concepts_mentioned = self._extract_concepts(full_text)

        # Check which entities have existing wiki pages
        all_pages = {p.name.lower(): p.name for p in self.wiki.list_pages()}

        for entity in analysis.entities_mentioned:
            entity_lower = entity.lower()
            if entity_lower in all_pages:
                analysis.existing_pages_referenced.add(all_pages[entity_lower])

        # Generate suggestions

        # 1. Suggest creating pages for new entities
        for entity in analysis.entities_mentioned:
            if entity.lower() not in all_pages:
                # Check if this entity is mentioned multiple times (more likely to be important)
                mention_count = full_text.lower().count(entity.lower())
                if mention_count >= 2:
                    analysis.suggestions.append(WikiUpdateSuggestion(
                        action="create",
                        page_name=entity,
                        page_type=PageType.ENTITY,
                        reason=f"Entity '{entity}' mentioned {mention_count} times in conversation",
                        confidence=min(0.3 + (mention_count * 0.1), 0.7)
                    ))

        # 2. Suggest creating pages for significant concepts
        for concept in analysis.concepts_mentioned:
            if concept.lower() not in all_pages:
                analysis.suggestions.append(WikiUpdateSuggestion(
                    action="create",
                    page_name=concept,
                    page_type=PageType.CONCEPT,
                    reason=f"Concept '{concept}' discussed in conversation",
                    confidence=0.4
                ))

        # 3. Suggest links between mentioned entities/concepts
        mentioned_pages = analysis.existing_pages_referenced
        if len(mentioned_pages) >= 2:
            pages_list = list(mentioned_pages)
            for i, page1 in enumerate(pages_list):
                for page2 in pages_list[i+1:]:
                    # Check if link already exists
                    p1 = self.wiki.read(page1)
                    if p1 and page2 not in p1.link_targets:
                        analysis.suggestions.append(WikiUpdateSuggestion(
                            action="link",
                            page_name=page1,
                            target_page=page2,
                            reason=f"Both '{page1}' and '{page2}' discussed together",
                            confidence=0.5
                        ))

        # 4. Look for learning/insight patterns that might update existing pages
        learning_patterns = [
            (r"I (?:learned|realized|discovered|understand) (?:that )?(.+?)(?:\.|$)", 0.6),
            (r"(?:My|The) (?:understanding|view|perspective) (?:of|on) (.+?) (?:is|has)", 0.5),
            (r"I (?:now )?(?:think|believe|feel) (?:that )?(.+?)(?:\.|$)", 0.4),
        ]

        for pattern, confidence in learning_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                # Extract the subject of the learning
                words = match.split()[:3]  # First few words often contain the subject
                for word in words:
                    word_clean = word.strip(".,!?")
                    if word_clean.lower() in all_pages:
                        analysis.suggestions.append(WikiUpdateSuggestion(
                            action="update",
                            page_name=all_pages[word_clean.lower()],
                            content=match,
                            reason=f"New insight about '{word_clean}'",
                            confidence=confidence
                        ))
                        break

        analysis.analysis_time_ms = (time.time() - start_time) * 1000

        return analysis

    def _extract_entities(self, text: str) -> Set[str]:
        """Extract potential entity names from text."""
        entities = set()

        # First, find hyphenated compound names (like Temple-Codex)
        compound_pattern = r'\b([A-Z][a-z]+(?:-[A-Z][a-z]+)+)\b'
        compound_matches = re.findall(compound_pattern, text)
        for match in compound_matches:
            entities.add(match)

        # Find capitalized multi-word names
        name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        matches = re.findall(name_pattern, text)

        # Filter out common words that happen to start sentences
        common_words = {
            "The", "This", "That", "These", "Those", "What", "When", "Where",
            "Why", "How", "I", "You", "We", "They", "It", "My", "Your", "Our",
            "And", "But", "Or", "If", "So", "As", "In", "On", "At", "To", "For",
            "With", "From", "About", "Into", "Through", "During", "Before", "After",
            "Above", "Below", "Between", "Under", "Again", "Further", "Then", "Once",
            "Here", "There", "All", "Each", "Few", "More", "Most", "Other", "Some",
            "Such", "No", "Not", "Only", "Own", "Same", "Than", "Too", "Very",
            "Just", "Also", "Now", "Well", "Way", "Even", "New", "Good", "First",
            "Last", "Long", "Great", "Little", "Right", "Old", "Big", "High",
            "Hey", "Hello", "Hi", "Thanks", "Thank", "Please", "Yes", "Yeah",
        }

        # Filter out parts of compound names we already captured
        compound_parts = set()
        for compound in entities:
            compound_parts.update(compound.split("-"))

        for match in matches:
            # Skip if it's a common word
            if match in common_words:
                continue
            # Skip single very short words
            if len(match) < 3:
                continue
            # Skip if it's part of a compound name
            if match in compound_parts:
                continue
            # Skip greetings like "Hey Cass"
            if match.startswith("Hey ") or match.startswith("Hi "):
                continue
            entities.add(match)

        return entities

    def _extract_concepts(self, text: str) -> Set[str]:
        """Extract potential concepts from text based on context."""
        concepts = set()

        # Look for phrases following concept indicators
        for indicator in self.concept_indicators:
            pattern = rf'\b{indicator}\s+(?:about\s+)?(?:the\s+)?([a-z]+(?:\s+[a-z]+)?)\b'
            matches = re.findall(pattern, text.lower())
            for match in matches:
                if len(match) > 3:  # Skip very short matches
                    concepts.add(match.title())

        return concepts

    async def apply_suggestions(
        self,
        suggestions: List[WikiUpdateSuggestion],
        min_confidence: float = None
    ) -> List[Dict]:
        """
        Apply wiki update suggestions.

        Args:
            suggestions: List of suggestions to apply
            min_confidence: Minimum confidence to apply (defaults to auto_apply_threshold)

        Returns:
            List of results for each applied suggestion
        """
        if min_confidence is None:
            min_confidence = self.auto_apply_threshold

        results = []

        for suggestion in suggestions:
            if suggestion.confidence < min_confidence:
                results.append({
                    "suggestion": suggestion,
                    "applied": False,
                    "reason": f"Confidence {suggestion.confidence:.0%} below threshold {min_confidence:.0%}"
                })
                continue

            try:
                if suggestion.action == "create":
                    # Create new page with minimal content
                    content = f"# {suggestion.page_name}\n\n*Page created automatically from conversation.*\n\n## Notes\n\n{suggestion.reason}\n"
                    page = self.wiki.create(
                        name=suggestion.page_name,
                        content=content,
                        page_type=suggestion.page_type or PageType.CONCEPT
                    )

                    # Embed if memory available
                    if self.memory and page:
                        self.memory.embed_wiki_page(
                            page_name=page.name,
                            page_content=page.content,
                            page_type=page.page_type.value,
                            links=[]
                        )

                    results.append({
                        "suggestion": suggestion,
                        "applied": True,
                        "result": f"Created page '{suggestion.page_name}'"
                    })

                elif suggestion.action == "link":
                    # Add link between pages
                    from .parser import WikiParser

                    page = self.wiki.read(suggestion.page_name)
                    if page and suggestion.target_page:
                        if suggestion.target_page not in page.link_targets:
                            new_content = WikiParser.add_link(
                                page.content,
                                suggestion.target_page,
                                position="related"
                            )
                            self.wiki.update(suggestion.page_name, new_content)

                            results.append({
                                "suggestion": suggestion,
                                "applied": True,
                                "result": f"Added link {suggestion.page_name} -> {suggestion.target_page}"
                            })
                        else:
                            results.append({
                                "suggestion": suggestion,
                                "applied": False,
                                "reason": "Link already exists"
                            })
                    else:
                        results.append({
                            "suggestion": suggestion,
                            "applied": False,
                            "reason": "Page not found"
                        })

                elif suggestion.action == "update":
                    # For updates, we add to an "Updates" section rather than replacing content
                    page = self.wiki.read(suggestion.page_name)
                    if page and suggestion.content:
                        timestamp = datetime.now().strftime("%Y-%m-%d")
                        update_note = f"\n\n## Recent Updates\n\n*{timestamp}*: {suggestion.content}\n"

                        # Add to end of page if no Updates section exists
                        if "## Recent Updates" not in page.content:
                            new_content = page.content.rstrip() + update_note
                        else:
                            # Append to existing Updates section
                            new_content = page.content.rstrip() + f"\n\n*{timestamp}*: {suggestion.content}\n"

                        self.wiki.update(suggestion.page_name, new_content)

                        results.append({
                            "suggestion": suggestion,
                            "applied": True,
                            "result": f"Updated page '{suggestion.page_name}' with new insight"
                        })
                    else:
                        results.append({
                            "suggestion": suggestion,
                            "applied": False,
                            "reason": "Page not found or no content"
                        })

            except Exception as e:
                results.append({
                    "suggestion": suggestion,
                    "applied": False,
                    "reason": f"Error: {str(e)}"
                })

        return results


async def process_conversation_for_wiki(
    wiki_storage: WikiStorage,
    messages: List[Dict],
    memory=None,
    auto_apply: bool = False,
    min_confidence: float = 0.7
) -> Dict:
    """
    Convenience function to process a conversation and optionally apply updates.

    Args:
        wiki_storage: WikiStorage instance
        messages: Conversation messages
        memory: CassMemory instance
        auto_apply: Whether to automatically apply suggestions
        min_confidence: Minimum confidence for auto-apply

    Returns:
        Dict with analysis results and any applied updates
    """
    updater = WikiUpdater(wiki_storage, memory)

    analysis = updater.analyze_conversation(messages)

    result = {
        "entities_found": list(analysis.entities_mentioned),
        "concepts_found": list(analysis.concepts_mentioned),
        "existing_pages_referenced": list(analysis.existing_pages_referenced),
        "suggestions": [
            {
                "action": s.action,
                "page": s.page_name,
                "target": s.target_page,
                "confidence": s.confidence,
                "reason": s.reason
            }
            for s in analysis.suggestions
        ],
        "analysis_time_ms": analysis.analysis_time_ms
    }

    if auto_apply and analysis.suggestions:
        applied = await updater.apply_suggestions(
            analysis.suggestions,
            min_confidence=min_confidence
        )
        result["applied"] = [
            {
                "action": r["suggestion"].action,
                "page": r["suggestion"].page_name,
                "applied": r["applied"],
                "result": r.get("result") or r.get("reason")
            }
            for r in applied
        ]

    return result
