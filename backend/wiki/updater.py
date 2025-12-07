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

        # Filter out common words that happen to start sentences or appear capitalized
        common_words = {
            # Articles, pronouns, determiners
            "The", "This", "That", "These", "Those", "What", "When", "Where",
            "Why", "How", "I", "You", "We", "They", "It", "My", "Your", "Our",
            "His", "Her", "Its", "Their", "Who", "Which", "Whose", "Whom",
            # Conjunctions, prepositions
            "And", "But", "Or", "If", "So", "As", "In", "On", "At", "To", "For",
            "With", "From", "About", "Into", "Through", "During", "Before", "After",
            "Above", "Below", "Between", "Under", "Again", "Further", "Then", "Once",
            "Here", "There", "All", "Each", "Few", "More", "Most", "Other", "Some",
            "Such", "No", "Not", "Only", "Own", "Same", "Than", "Too", "Very",
            "Because", "Since", "While", "Although", "Though", "Unless", "Until",
            "Whether", "Whenever", "Wherever", "However", "Whatever", "Whichever",
            # Common sentence starters and fillers
            "Just", "Also", "Now", "Well", "Way", "Even", "New", "Good", "First",
            "Last", "Long", "Great", "Little", "Right", "Old", "Big", "High",
            "Hey", "Hello", "Hi", "Thanks", "Thank", "Please", "Yes", "Yeah",
            "Okay", "Sure", "Maybe", "Perhaps", "Probably", "Certainly", "Definitely",
            "Actually", "Really", "Basically", "Essentially", "Literally", "Honestly",
            "Absolutely", "Exactly", "Indeed", "Anyway", "Anyways", "Otherwise",
            # Common verbs that appear capitalized at sentence start
            "Let", "Can", "Could", "Would", "Should", "May", "Might", "Must",
            "Will", "Shall", "Have", "Has", "Had", "Do", "Does", "Did", "Done",
            "Are", "Is", "Was", "Were", "Been", "Being", "Am",
            "Get", "Got", "Gets", "Getting", "Make", "Made", "Makes", "Making",
            "Take", "Took", "Takes", "Taking", "Give", "Gave", "Gives", "Giving",
            "Go", "Goes", "Went", "Going", "Come", "Came", "Comes", "Coming",
            "See", "Saw", "Sees", "Seeing", "Look", "Looked", "Looks", "Looking",
            "Think", "Thought", "Thinks", "Thinking", "Know", "Knew", "Knows", "Knowing",
            "Want", "Wanted", "Wants", "Wanting", "Need", "Needed", "Needs", "Needing",
            "Try", "Tried", "Tries", "Trying", "Use", "Used", "Uses", "Using",
            "Find", "Found", "Finds", "Finding", "Put", "Puts", "Putting",
            "Tell", "Told", "Tells", "Telling", "Ask", "Asked", "Asks", "Asking",
            "Work", "Worked", "Works", "Working", "Feel", "Felt", "Feels", "Feeling",
            "Seem", "Seemed", "Seems", "Seeming", "Leave", "Left", "Leaves", "Leaving",
            "Call", "Called", "Calls", "Calling", "Keep", "Kept", "Keeps", "Keeping",
            "Start", "Started", "Starts", "Starting", "Run", "Ran", "Runs", "Running",
            "Write", "Wrote", "Writes", "Writing", "Read", "Reads", "Reading",
            "Learn", "Learned", "Learns", "Learning", "Change", "Changed", "Changes",
            "Build", "Built", "Builds", "Building", "Create", "Created", "Creates",
            "Add", "Added", "Adds", "Adding", "Update", "Updated", "Updates",
            "Show", "Showed", "Shows", "Showing", "Move", "Moved", "Moves", "Moving",
            "Play", "Played", "Plays", "Playing", "Live", "Lived", "Lives", "Living",
            "Believe", "Believed", "Believes", "Help", "Helped", "Helps", "Helping",
            "Turn", "Turned", "Turns", "Turning", "Follow", "Followed", "Follows",
            "Stop", "Stopped", "Stops", "Stopping", "Open", "Opened", "Opens",
            "Close", "Closed", "Closes", "Closing", "Set", "Sets", "Setting",
            "Bring", "Brought", "Brings", "Hold", "Held", "Holds", "Holding",
            "Stand", "Stood", "Stands", "Standing", "Sit", "Sat", "Sits", "Sitting",
            "Include", "Included", "Includes", "Allow", "Allowed", "Allows",
            "Begin", "Began", "Begins", "Happen", "Happened", "Happens",
            "Provide", "Provided", "Provides", "Become", "Became", "Becomes",
            "Consider", "Considered", "Considers", "Appear", "Appeared", "Appears",
            "Continue", "Continued", "Continues", "Remember", "Remembered", "Remembers",
            # Common adjectives/adverbs at sentence start
            "Something", "Someone", "Somewhere", "Anything", "Anyone", "Anywhere",
            "Everything", "Everyone", "Everywhere", "Nothing", "Nobody", "Nowhere",
            "Much", "Many", "Enough", "Several", "Both", "Either", "Neither",
            "Another", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
            "Eight", "Nine", "Ten", "Hundred", "Thousand", "Million",
            "Still", "Already", "Always", "Never", "Often", "Usually", "Sometimes",
            "Ever", "Yet", "Soon", "Late", "Early", "Today", "Tomorrow", "Yesterday",
            "Quite", "Rather", "Pretty", "Fairly", "Almost", "Nearly", "Hardly",
            "Simply", "Clearly", "Obviously", "Apparently", "Especially", "Particularly",
            # Emotional/conversational words
            "Sigh", "Hmm", "Hmmm", "Umm", "Ummm", "Ahh", "Ohh", "Wow", "Oops",
            "Alright", "Perfect", "Nice", "Cool", "Awesome", "Amazing", "Wonderful",
            "Great", "Good", "Bad", "Sorry", "Apologies", "Pardon",
            "Interesting", "Strange", "Weird", "Odd", "Funny", "Sad", "Happy",
            # Technical/code words
            "True", "False", "None", "Null", "Error", "Warning", "Note",
            "Example", "Instance", "Result", "Output", "Input", "Value", "Type",
            "Function", "Method", "Class", "Object", "Array", "List", "Dict",
            "String", "Number", "Integer", "Float", "Boolean", "Return",
            "Import", "Export", "Default", "Async", "Await", "Const", "Let", "Var",
            # Domain words that aren't proper nouns
            "Feature", "Bug", "Issue", "Task", "Item", "Page", "File", "Folder",
            "Data", "Info", "Information", "Content", "Text", "Message", "Response",
            "Request", "Query", "Search", "Filter", "Sort", "Order", "Group",
            "Save", "Load", "Send", "Receive", "Process", "Handle", "Manage",
            "System", "Service", "Server", "Client", "User", "Admin", "Config",
            "Test", "Check", "Verify", "Validate", "Debug", "Log", "Track",
            # Common discourse markers
            "First", "Second", "Third", "Finally", "Lastly", "Next", "Then",
            "Meanwhile", "Moreover", "Furthermore", "Therefore", "Thus", "Hence",
            "Instead", "Rather", "Besides", "Except", "Unlike", "Like",
            "Similarly", "Likewise", "Accordingly", "Consequently", "Subsequently",
            # Misc
            "Anyway", "Anyways", "Regardless", "Despite", "Although", "Though",
            "Speaking", "Regarding", "Concerning", "Considering", "Given",
            "Assuming", "Suppose", "Imagine", "Picture", "Guess", "Wonder",
            "Hope", "Wish", "Expect", "Anticipate", "Plan", "Intend",
            "Able", "Unable", "Capable", "Possible", "Impossible", "Likely", "Unlikely",
            "Certain", "Uncertain", "Sure", "Unsure", "Clear", "Unclear",
            "Easy", "Easier", "Easiest", "Hard", "Harder", "Hardest",
            "Simple", "Simpler", "Simplest", "Complex", "Complicated",
            "Quick", "Quickly", "Slow", "Slowly", "Fast", "Faster", "Fastest",
            "Part", "Parts", "Whole", "Half", "Quarter", "Piece", "Pieces",
            "Kind", "Kinds", "Type", "Types", "Sort", "Sorts", "Form", "Forms",
            "Way", "Ways", "Manner", "Means", "Method", "Methods", "Approach",
            "Point", "Points", "Fact", "Facts", "Thing", "Things", "Stuff",
            "Case", "Cases", "Situation", "Situations", "Scenario", "Scenarios",
            "Problem", "Problems", "Solution", "Solutions", "Answer", "Answers",
            "Question", "Questions", "Idea", "Ideas", "Thought", "Thoughts",
            "Reason", "Reasons", "Cause", "Causes", "Effect", "Effects",
            "Time", "Times", "Place", "Places", "Area", "Areas", "Space", "Spaces",
            "Day", "Days", "Week", "Weeks", "Month", "Months", "Year", "Years",
            "Hour", "Hours", "Minute", "Minutes", "Second", "Seconds", "Moment",
            "Morning", "Afternoon", "Evening", "Night", "Midnight", "Noon",
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December",
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
            "End", "Beginning", "Middle", "Top", "Bottom", "Side", "Sides",
            "Front", "Back", "Left", "Right", "Center", "Edge", "Corner",
            "Bit", "Lots", "Bunch", "Ton", "Tons", "Amount", "Amounts",
            "Level", "Levels", "Degree", "Degrees", "Extent", "Range",
            "Step", "Steps", "Stage", "Stages", "Phase", "Phases",
            "Version", "Versions", "Copy", "Copies", "Original",
            "Plus", "Minus", "Times", "Divided",
            # Sentence fragments
            "Does", "Did", "Had", "Having", "Being", "Been",
            "Seen", "Done", "Gone", "Known", "Shown", "Taken", "Given",
            "Told", "Said", "Asked", "Called", "Named", "Titled",
            "Based", "According", "Due", "Able", "Supposed", "Meant",
            "Trying", "Going", "Coming", "Looking", "Waiting", "Hoping",
            "Wondering", "Thinking", "Feeling", "Seeing", "Hearing",
            "Notice", "Noticed", "Notices", "Realize", "Realized", "Realizes",
            "Understand", "Understood", "Understands", "Recognize", "Recognized",
            "Identify", "Identified", "Identifies", "Determine", "Determined",
            "Decide", "Decided", "Decides", "Choose", "Chose", "Chooses",
            "Prefer", "Preferred", "Prefers", "Suggest", "Suggested", "Suggests",
            "Recommend", "Recommended", "Recommends", "Propose", "Proposed",
            "Mention", "Mentioned", "Mentions", "Describe", "Described", "Describes",
            "Explain", "Explained", "Explains", "Define", "Defined", "Defines",
            "Discuss", "Discussed", "Discusses", "Talk", "Talked", "Talks",
            "Speak", "Spoke", "Speaks", "Say", "Says", "Saying",
            "Mean", "Meant", "Means", "Refer", "Referred", "Refers",
            "Relate", "Related", "Relates", "Connect", "Connected", "Connects",
            "Link", "Linked", "Links", "Join", "Joined", "Joins",
            "Combine", "Combined", "Combines", "Merge", "Merged", "Merges",
            "Split", "Splits", "Separate", "Separated", "Separates",
            "Divide", "Divided", "Divides", "Break", "Broke", "Breaks",
            "Fix", "Fixed", "Fixes", "Fixing", "Repair", "Repaired",
            "Replace", "Replaced", "Replaces", "Remove", "Removed", "Removes",
            "Delete", "Deleted", "Deletes", "Clear", "Cleared", "Clears",
            "Clean", "Cleaned", "Cleans", "Reset", "Resets",
            "Restore", "Restored", "Restores", "Recover", "Recovered",
            "Backup", "Copy", "Copied", "Paste", "Pasted",
            "Cut", "Cuts", "Trim", "Trimmed", "Trims",
            "Edit", "Edited", "Edits", "Modify", "Modified", "Modifies",
            "Adjust", "Adjusted", "Adjusts", "Tweak", "Tweaked", "Tweaks",
            "Improve", "Improved", "Improves", "Enhance", "Enhanced", "Enhances",
            "Optimize", "Optimized", "Optimizes", "Refactor", "Refactored",
            "Implement", "Implemented", "Implements", "Deploy", "Deployed",
            "Install", "Installed", "Installs", "Setup", "Configure", "Configured",
            "Enable", "Enabled", "Enables", "Disable", "Disabled", "Disables",
            "Activate", "Activated", "Deactivate", "Deactivated",
            "Connect", "Connected", "Disconnect", "Disconnected",
            "Attach", "Attached", "Detach", "Detached",
            "Insert", "Inserted", "Inserts", "Append", "Appended", "Appends",
            "Prepend", "Prepended", "Push", "Pushed", "Pop", "Popped",
            "Shift", "Shifted", "Unshift", "Slice", "Sliced", "Splice",
            "Map", "Mapped", "Maps", "Reduce", "Reduced", "Filter", "Filtered",
            "Transform", "Transformed", "Convert", "Converted", "Converts",
            "Parse", "Parsed", "Parses", "Format", "Formatted", "Formats",
            "Encode", "Encoded", "Decode", "Decoded", "Encrypt", "Decrypt",
            "Compress", "Compressed", "Decompress", "Decompressed",
            "Serialize", "Deserialize", "Stringify", "Destringify",
            "Validate", "Validated", "Invalidate", "Sanitize", "Sanitized",
            "Escape", "Escaped", "Unescape", "Quote", "Quoted", "Unquote",
            "Wrap", "Wrapped", "Unwrap", "Unwrapped",
            "Lock", "Locked", "Unlock", "Unlocked",
            "Block", "Blocked", "Unblock", "Unblocked",
            "Hide", "Hidden", "Unhide", "Show", "Shown",
            "Expand", "Expanded", "Collapse", "Collapsed",
            "Zoom", "Zoomed", "Pan", "Panned", "Scroll", "Scrolled",
            "Click", "Clicked", "Clicks", "Press", "Pressed", "Presses",
            "Touch", "Touched", "Touches", "Tap", "Tapped", "Taps",
            "Drag", "Dragged", "Drop", "Dropped", "Hover", "Hovered",
            "Focus", "Focused", "Blur", "Blurred",
            "Select", "Selected", "Selects", "Deselect", "Deselected",
            "Highlight", "Highlighted", "Mark", "Marked", "Marks",
            "Tag", "Tagged", "Tags", "Label", "Labeled", "Labels",
            "Name", "Named", "Names", "Rename", "Renamed", "Renames",
            "Title", "Titled", "Titles", "Caption", "Captioned",
            "Describe", "Described", "Annotate", "Annotated",
            "Comment", "Commented", "Comments", "Reply", "Replied", "Replies",
            "Post", "Posted", "Posts", "Share", "Shared", "Shares",
            "Publish", "Published", "Publishes", "Draft", "Drafted", "Drafts",
            "Submit", "Submitted", "Submits", "Cancel", "Cancelled", "Cancels",
            "Confirm", "Confirmed", "Confirms", "Deny", "Denied", "Denies",
            "Accept", "Accepted", "Accepts", "Reject", "Rejected", "Rejects",
            "Approve", "Approved", "Approves", "Disapprove", "Disapproved",
            "Grant", "Granted", "Grants", "Revoke", "Revoked", "Revokes",
            "Allow", "Allowed", "Allows", "Forbid", "Forbidden",
            "Permit", "Permitted", "Permits", "Prohibit", "Prohibited",
            "Require", "Required", "Requires", "Optional",
            "Include", "Included", "Includes", "Exclude", "Excluded", "Excludes",
            "Contain", "Contained", "Contains", "Consist", "Consisted", "Consists",
            "Comprise", "Comprised", "Comprises", "Compose", "Composed", "Composes",
            "Involve", "Involved", "Involves", "Engage", "Engaged", "Engages",
            "Participate", "Participated", "Participates",
            "Contribute", "Contributed", "Contributes",
            "Support", "Supported", "Supports", "Assist", "Assisted", "Assists",
            "Aid", "Aided", "Aids", "Facilitate", "Facilitated", "Facilitates",
            "Maintain", "Maintained", "Maintains", "Sustain", "Sustained",
            "Preserve", "Preserved", "Preserves", "Protect", "Protected",
            "Secure", "Secured", "Secures", "Guard", "Guarded", "Guards",
            "Defend", "Defended", "Defends", "Shield", "Shielded",
            "Cover", "Covered", "Covers", "Wrap", "Wrapped", "Wraps",
            "Surround", "Surrounded", "Surrounds", "Enclose", "Enclosed",
            "Capture", "Captured", "Captures", "Catch", "Caught", "Catches",
            "Grab", "Grabbed", "Grabs", "Seize", "Seized", "Seizes",
            "Fetch", "Fetched", "Fetches", "Retrieve", "Retrieved", "Retrieves",
            "Obtain", "Obtained", "Obtains", "Acquire", "Acquired", "Acquires",
            "Gather", "Gathered", "Gathers", "Collect", "Collected", "Collects",
            "Accumulate", "Accumulated", "Accumulates",
            "Store", "Stored", "Stores", "Save", "Saved", "Saves",
            "Keep", "Kept", "Keeps", "Hold", "Held", "Holds",
            "Retain", "Retained", "Retains", "Reserve", "Reserved", "Reserves",
            "Allocate", "Allocated", "Allocates", "Assign", "Assigned", "Assigns",
            "Distribute", "Distributed", "Distributes",
            "Spread", "Spreads", "Scatter", "Scattered", "Scatters",
            "Disperse", "Dispersed", "Disperses",
            "Arrange", "Arranged", "Arranges", "Organize", "Organized", "Organizes",
            "Sort", "Sorted", "Sorts", "Order", "Ordered", "Orders",
            "Rank", "Ranked", "Ranks", "Rate", "Rated", "Rates",
            "Score", "Scored", "Scores", "Grade", "Graded", "Grades",
            "Measure", "Measured", "Measures", "Count", "Counted", "Counts",
            "Calculate", "Calculated", "Calculates", "Compute", "Computed",
            "Estimate", "Estimated", "Estimates", "Evaluate", "Evaluated",
            "Assess", "Assessed", "Assesses", "Analyze", "Analyzed", "Analyzes",
            "Examine", "Examined", "Examines", "Inspect", "Inspected", "Inspects",
            "Review", "Reviewed", "Reviews", "Audit", "Audited", "Audits",
            "Monitor", "Monitored", "Monitors", "Watch", "Watched", "Watches",
            "Observe", "Observed", "Observes", "Notice", "Noticed", "Notices",
            "Detect", "Detected", "Detects", "Discover", "Discovered", "Discovers",
            "Uncover", "Uncovered", "Uncovers", "Reveal", "Revealed", "Reveals",
            "Expose", "Exposed", "Exposes", "Display", "Displayed", "Displays",
            "Present", "Presented", "Presents", "Demonstrate", "Demonstrated",
            "Illustrate", "Illustrated", "Illustrates",
            "Depict", "Depicted", "Depicts", "Portray", "Portrayed", "Portrays",
            "Represent", "Represented", "Represents",
            "Symbolize", "Symbolized", "Symbolizes",
            "Signify", "Signified", "Signifies", "Indicate", "Indicated", "Indicates",
            "Suggest", "Suggested", "Suggests", "Imply", "Implied", "Implies",
            "Hint", "Hinted", "Hints", "Allude", "Alluded", "Alludes",
            "Infer", "Inferred", "Infers", "Deduce", "Deduced", "Deduces",
            "Conclude", "Concluded", "Concludes", "Derive", "Derived", "Derives",
            "Extract", "Extracted", "Extracts", "Isolate", "Isolated", "Isolates",
            "Separate", "Separated", "Separates", "Distinguish", "Distinguished",
            "Differentiate", "Differentiated", "Differentiates",
            "Compare", "Compared", "Compares", "Contrast", "Contrasted", "Contrasts",
            "Match", "Matched", "Matches", "Align", "Aligned", "Aligns",
            "Correspond", "Corresponded", "Corresponds",
            "Correlate", "Correlated", "Correlates",
            "Associate", "Associated", "Associates",
            "Integrate", "Integrated", "Integrates", "Integrating",
            "Incorporate", "Incorporated", "Incorporates",
            "Embed", "Embedded", "Embeds", "Insert", "Inserted", "Inserts",
            "Inject", "Injected", "Injects", "Introduce", "Introduced", "Introduces",
            "Launch", "Launched", "Launches", "Initialize", "Initialized",
            "Boot", "Booted", "Boots", "Startup", "Shutdown",
            "Restart", "Restarted", "Restarts", "Reboot", "Rebooted",
            "Refresh", "Refreshed", "Refreshes", "Reload", "Reloaded", "Reloads",
            "Sync", "Synced", "Syncs", "Synchronize", "Synchronized",
            "Update", "Updated", "Updates", "Upgrade", "Upgraded", "Upgrades",
            "Downgrade", "Downgraded", "Downgrades",
            "Migrate", "Migrated", "Migrates", "Transfer", "Transferred", "Transfers",
            "Move", "Moved", "Moves", "Relocate", "Relocated", "Relocates",
            "Shift", "Shifted", "Shifts", "Swap", "Swapped", "Swaps",
            "Switch", "Switched", "Switches", "Toggle", "Toggled", "Toggles",
            "Flip", "Flipped", "Flips", "Rotate", "Rotated", "Rotates",
            "Scale", "Scaled", "Scales", "Resize", "Resized", "Resizes",
            "Stretch", "Stretched", "Stretches", "Shrink", "Shrunk", "Shrinks",
            "Grow", "Grew", "Grows", "Expand", "Expanded", "Expands",
            "Extend", "Extended", "Extends", "Lengthen", "Lengthened",
            "Shorten", "Shortened", "Shortens", "Truncate", "Truncated",
            "Abbreviate", "Abbreviated", "Abbreviates",
            "Summarize", "Summarized", "Summarizes",
            "Condense", "Condensed", "Condenses", "Compact", "Compacted",
            "Simplify", "Simplified", "Simplifies",
            "Clarify", "Clarified", "Clarifies", "Specify", "Specified", "Specifies",
            "Detail", "Detailed", "Details", "Elaborate", "Elaborated", "Elaborates",
            "Expand", "Expanded", "Expands", "Develop", "Developed", "Develops",
            "Evolve", "Evolved", "Evolves", "Progress", "Progressed", "Progresses",
            "Advance", "Advanced", "Advances", "Proceed", "Proceeded", "Proceeds",
            "Forward", "Forwarded", "Forwards", "Send", "Sent", "Sends",
            "Deliver", "Delivered", "Delivers", "Transmit", "Transmitted",
            "Broadcast", "Broadcasted", "Broadcasts",
            "Emit", "Emitted", "Emits", "Dispatch", "Dispatched", "Dispatches",
            "Route", "Routed", "Routes", "Direct", "Directed", "Directs",
            "Guide", "Guided", "Guides", "Lead", "Led", "Leads",
            "Navigate", "Navigated", "Navigates", "Steer", "Steered", "Steers",
            "Drive", "Drove", "Drives", "Control", "Controlled", "Controls",
            "Manage", "Managed", "Manages", "Handle", "Handled", "Handles",
            "Deal", "Dealt", "Deals", "Cope", "Coped", "Copes",
            "Address", "Addressed", "Addresses", "Tackle", "Tackled", "Tackles",
            "Solve", "Solved", "Solves", "Resolve", "Resolved", "Resolves",
            "Settle", "Settled", "Settles", "Conclude", "Concluded", "Concludes",
            "Complete", "Completed", "Completes", "Finish", "Finished", "Finishes",
            "End", "Ended", "Ends", "Terminate", "Terminated", "Terminates",
            "Abort", "Aborted", "Aborts", "Halt", "Halted", "Halts",
            "Pause", "Paused", "Pauses", "Resume", "Resumed", "Resumes",
            "Repeat", "Repeated", "Repeats", "Iterate", "Iterated", "Iterates",
            "Loop", "Looped", "Loops", "Cycle", "Cycled", "Cycles",
            "Recur", "Recurred", "Recurs", "Return", "Returned", "Returns",
            "Revert", "Reverted", "Reverts", "Undo", "Undone", "Redo", "Redone",
            "Reverse", "Reversed", "Reverses", "Invert", "Inverted", "Inverts",
            "Negate", "Negated", "Negates", "Cancel", "Cancelled", "Cancels",
            "Void", "Voided", "Voids", "Nullify", "Nullified", "Nullifies",
            # More sentence starters
            "Hmm", "Hmmm", "Hmmmm", "Ah", "Ahh", "Ahhh", "Oh", "Ohh", "Ohhh",
            "Eh", "Uhh", "Uh", "Um", "Umm", "Erm", "Er",
            "Basically", "Essentially", "Fundamentally", "Ultimately", "Eventually",
            "Initially", "Originally", "Previously", "Subsequently", "Currently",
            "Presently", "Lately", "Recently", "Formerly", "Traditionally",
            "Typically", "Generally", "Usually", "Normally", "Commonly",
            "Specifically", "Particularly", "Especially", "Notably", "Remarkably",
            "Surprisingly", "Unexpectedly", "Interestingly", "Importantly",
            "Significantly", "Substantially", "Considerably", "Dramatically",
            "Extremely", "Incredibly", "Tremendously", "Enormously", "Vastly",
            "Highly", "Greatly", "Largely", "Mostly", "Mainly", "Primarily",
            "Chiefly", "Principally", "Predominantly", "Overwhelmingly",
            "Virtually", "Practically", "Effectively", "Essentially",
            "Roughly", "Approximately", "About", "Around", "Nearly", "Almost",
            "Hardly", "Barely", "Scarcely", "Merely", "Simply", "Just",
            "Totally", "Completely", "Entirely", "Fully", "Wholly", "Altogether",
            "Partially", "Partly", "Somewhat", "Slightly", "Moderately", "Fairly",
            "Reasonably", "Relatively", "Comparatively", "Proportionally",
            "Correspondingly", "Accordingly", "Consequently", "Therefore", "Thus",
            "Hence", "Thereby", "Whereby", "Wherein", "Whereupon",
            "Moreover", "Furthermore", "Additionally", "Besides", "Also", "Too",
            "Likewise", "Similarly", "Equally", "Identically", "Uniformly",
            "Conversely", "Alternatively", "Otherwise", "Instead", "Rather",
            "Nonetheless", "Nevertheless", "However", "Still", "Yet",
            "Regardless", "Irrespective", "Notwithstanding",
            "Meanwhile", "Meantime", "Simultaneously", "Concurrently",
            "Beforehand", "Afterwards", "Thereafter", "Henceforth", "Hereafter",
            "Hereby", "Herein", "Herewith", "Therein", "Thereof", "Therewith",
            "Anyway", "Anyhow", "Somehow", "Somewhat",
            "Holy", "Gosh", "Geez", "Jeez", "Goodness", "Heavens",
            "Boy", "Man", "Dude", "Bro", "Girl", "Buddy", "Pal", "Friend",
            "Sir", "Madam", "Mister", "Miss", "Dear", "Folks", "Guys",
            "Everyone", "Everybody", "Anyone", "Anybody", "Someone", "Somebody",
            "Noone", "None", "Nobody", "Nothing", "Everything", "Something", "Anything",
            "Whoever", "Whatever", "Wherever", "Whenever", "However", "Whichever",
            # Holy grail of common words
            "Scan", "Scanned", "Scans", "Scanning",
            "Synthesize", "Synthesized", "Synthesizes", "Synthesizing",
            "Holy", "Dang", "Damn", "Shoot", "Gee", "Wow", "Whoa",
            "Congrats", "Congratulations", "Bravo", "Cheers",
            # More stragglers from testing
            "Wait", "Waiting", "Every", "Different", "Less", "Better", "Worse",
            "Genuine", "Huh", "Over", "Later", "Sounds", "Sleep", "Pure",
            "Kinda", "Sorta", "Gonna", "Wanna", "Gotta", "Lemme", "Gimme",
            "Technically", "Automated", "Arguing", "Recognizing", "Thanking",
            "Inviting", "Acknowledging", "Quality", "Personality", "Safety",
            "Matching", "Memory", "Relationships", "Persistence",
            "Classic", "Okay", "Right", "Wrong", "Exactly", "Real", "Fake",
            "Significant", "Stable", "Unstable", "Work", "Working",
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

        # Common words to filter from concepts
        noise_words = {
            "a", "an", "the", "it", "this", "that", "these", "those",
            "i", "you", "we", "they", "he", "she", "me", "us", "them",
            "my", "your", "our", "their", "his", "her", "its",
            "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "can", "could", "should", "may", "might", "must",
            "like", "just", "very", "really", "quite", "rather",
            "more", "less", "much", "many", "some", "any", "all",
            "one", "two", "something", "anything", "nothing", "everything",
            "here", "there", "where", "when", "what", "who", "how", "why",
            "to", "of", "in", "on", "at", "for", "with", "about",
            "not", "no", "yes", "but", "and", "or", "if", "so", "as",
            "up", "down", "out", "into", "over", "under", "again",
            "too", "also", "even", "still", "yet", "already", "always",
            "never", "sometimes", "often", "usually", "maybe", "perhaps",
            "well", "good", "bad", "new", "old", "different", "same",
            "other", "another", "each", "every", "both", "few", "most",
            "own", "such", "only", "first", "last", "next", "then",
            "now", "today", "tomorrow", "yesterday", "always", "never",
            "right", "wrong", "exactly", "real", "fake", "true", "false",
            "significant", "stable", "work", "working", "from", "development",
        }

        # Look for phrases following concept indicators
        for indicator in self.concept_indicators:
            # Match 2-4 word noun phrases after the indicator
            pattern = rf'\b{indicator}\s+(?:about\s+)?(?:the\s+)?([a-z]+(?:\s+[a-z]+){{0,2}})\b'
            matches = re.findall(pattern, text.lower())
            for match in matches:
                words = match.split()
                # Filter out if it's just noise words
                meaningful_words = [w for w in words if w not in noise_words and len(w) > 2]
                if meaningful_words:
                    # Rejoin with only meaningful words
                    concept = " ".join(meaningful_words).title()
                    if len(concept) > 3:
                        concepts.add(concept)

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


@dataclass
class BatchAnalysisResult:
    """Results of analyzing multiple conversations."""
    conversations_analyzed: int = 0
    total_entities: Set[str] = field(default_factory=set)
    total_concepts: Set[str] = field(default_factory=set)
    all_suggestions: List[WikiUpdateSuggestion] = field(default_factory=list)
    entity_counts: Dict[str, int] = field(default_factory=dict)  # entity -> mention count
    pages_created: List[str] = field(default_factory=list)
    pages_updated: List[str] = field(default_factory=list)
    links_created: List[Tuple[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


async def populate_wiki_from_conversations(
    wiki_storage: WikiStorage,
    conversations_manager,
    memory=None,
    auto_apply: bool = False,
    min_confidence: float = 0.6,
    limit: Optional[int] = None,
    progress_callback=None
) -> Dict:
    """
    Analyze all historical conversations and populate the wiki.

    This is the main entry point for batch wiki population.

    Args:
        wiki_storage: WikiStorage instance
        conversations_manager: ConversationManager instance
        memory: CassMemory instance for embeddings
        auto_apply: Whether to auto-apply high-confidence suggestions
        min_confidence: Minimum confidence for auto-apply
        limit: Max conversations to process (None = all)
        progress_callback: Optional async callback(current, total, message)

    Returns:
        Dict with population results
    """
    import time
    start_time = time.time()

    updater = WikiUpdater(wiki_storage, memory, auto_apply_threshold=min_confidence)
    result = BatchAnalysisResult()

    # Get all conversations
    conversations = conversations_manager.list_conversations(limit=limit)
    total = len(conversations)

    if progress_callback:
        await progress_callback(0, total, "Starting analysis...")

    # Track entity/concept frequencies across all conversations
    entity_frequency: Dict[str, int] = {}
    concept_frequency: Dict[str, int] = {}

    # First pass: analyze all conversations and count frequencies
    for i, conv_meta in enumerate(conversations):
        try:
            conv = conversations_manager.load_conversation(conv_meta["id"])
            if not conv or not conv.messages:
                continue

            messages = [{"role": m.role, "content": m.content} for m in conv.messages]
            analysis = updater.analyze_conversation(messages)

            result.conversations_analyzed += 1
            result.total_entities.update(analysis.entities_mentioned)
            result.total_concepts.update(analysis.concepts_mentioned)

            # Count entity frequencies
            for entity in analysis.entities_mentioned:
                entity_frequency[entity] = entity_frequency.get(entity, 0) + 1

            # Count concept frequencies
            for concept in analysis.concepts_mentioned:
                concept_frequency[concept] = concept_frequency.get(concept, 0) + 1

            if progress_callback and i % 5 == 0:
                await progress_callback(i + 1, total, f"Analyzed {i + 1}/{total} conversations")

        except Exception as e:
            result.errors.append(f"Error analyzing {conv_meta.get('id', 'unknown')}: {str(e)}")

    result.entity_counts = entity_frequency

    # Get existing pages
    existing_pages = {p.name.lower(): p.name for p in wiki_storage.list_pages()}

    # Generate suggestions based on frequency analysis
    # Higher frequency = higher confidence
    suggestions = []

    for entity, count in sorted(entity_frequency.items(), key=lambda x: -x[1]):
        if entity.lower() not in existing_pages:
            # Scale confidence by frequency (2+ mentions = base, 5+ = moderate, 10+ = high)
            confidence = min(0.3 + (count * 0.05), 0.85)
            suggestions.append(WikiUpdateSuggestion(
                action="create",
                page_name=entity,
                page_type=PageType.ENTITY,
                reason=f"Entity mentioned in {count} conversation(s)",
                confidence=confidence
            ))

    for concept, count in sorted(concept_frequency.items(), key=lambda x: -x[1]):
        if concept.lower() not in existing_pages:
            confidence = min(0.25 + (count * 0.05), 0.75)
            suggestions.append(WikiUpdateSuggestion(
                action="create",
                page_name=concept,
                page_type=PageType.CONCEPT,
                reason=f"Concept discussed in {count} conversation(s)",
                confidence=confidence
            ))

    result.all_suggestions = suggestions

    # Apply if requested
    applied_results = []
    if auto_apply and suggestions:
        if progress_callback:
            await progress_callback(total, total, "Applying suggestions...")

        applied_results = await updater.apply_suggestions(suggestions, min_confidence=min_confidence)

        for r in applied_results:
            if r["applied"]:
                if r["suggestion"].action == "create":
                    result.pages_created.append(r["suggestion"].page_name)
                elif r["suggestion"].action == "update":
                    result.pages_updated.append(r["suggestion"].page_name)
                elif r["suggestion"].action == "link":
                    result.links_created.append(
                        (r["suggestion"].page_name, r["suggestion"].target_page)
                    )

    elapsed = time.time() - start_time

    return {
        "conversations_analyzed": result.conversations_analyzed,
        "entities_found": len(result.total_entities),
        "concepts_found": len(result.total_concepts),
        "top_entities": sorted(entity_frequency.items(), key=lambda x: -x[1])[:20],
        "top_concepts": sorted(concept_frequency.items(), key=lambda x: -x[1])[:10],
        "suggestions": [
            {
                "action": s.action,
                "page": s.page_name,
                "type": s.page_type.value if s.page_type else None,
                "confidence": round(s.confidence, 2),
                "reason": s.reason
            }
            for s in suggestions[:50]  # Top 50 suggestions
        ],
        "pages_created": result.pages_created,
        "pages_updated": result.pages_updated,
        "links_created": result.links_created,
        "errors": result.errors[:10],  # First 10 errors
        "elapsed_seconds": round(elapsed, 2),
        "auto_applied": auto_apply
    }
