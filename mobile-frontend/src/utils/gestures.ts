/**
 * Gesture and emote tag parsing utilities
 *
 * Tag formats:
 * - <gesture:think>...</gesture:think> - Wraps internal reasoning (collapsible)
 * - <gesture:wave> - Inline gesture marker
 * - <emote:happy> - Inline emote marker
 */

export interface ParsedMessage {
  /** Clean text with gesture/emote tags removed */
  text: string;
  /** Internal reasoning content if present */
  thinking: string | null;
  /** Extracted gesture names */
  gestures: string[];
  /** Extracted emote names */
  emotes: string[];
}

/**
 * Parse message content to extract gesture/emote tags
 */
export function parseGestureTags(content: string): ParsedMessage {
  const gestures: string[] = [];
  const emotes: string[] = [];
  let thinking: string | null = null;

  // Extract internal reasoning content - any tag containing "think" in name
  // Matches: <thinking>, <gesture:think>, etc.
  const thinkMatch = content.match(/<([\w:]*think[\w:]*)>([\s\S]*?)<\/\1>/i);
  if (thinkMatch) {
    thinking = thinkMatch[2].trim();
  }

  // Remove all thinking blocks from content
  let cleanText = content.replace(/<([\w:]*think[\w:]*)>[\s\S]*?<\/\1>/gi, '');

  // Extract and remove inline gesture tags: <gesture:name>
  cleanText = cleanText.replace(/<gesture:(\w+)>/g, (_, name) => {
    if (!gestures.includes(name)) {
      gestures.push(name);
    }
    return '';
  });

  // Extract and remove inline emote tags: <emote:name>
  cleanText = cleanText.replace(/<emote:(\w+)>/g, (_, name) => {
    if (!emotes.includes(name)) {
      emotes.push(name);
    }
    return '';
  });

  // Clean up whitespace
  cleanText = cleanText.trim().replace(/\n{3,}/g, '\n\n');

  return {
    text: cleanText,
    thinking,
    gestures,
    emotes,
  };
}
