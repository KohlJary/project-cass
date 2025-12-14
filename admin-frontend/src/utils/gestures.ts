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

  // Extract <gesture:think>...</gesture:think> content
  const thinkMatch = content.match(/<gesture:think>([\s\S]*?)<\/gesture:think>/);
  if (thinkMatch) {
    thinking = thinkMatch[1].trim();
  }

  // Remove thinking blocks from content
  let cleanText = content.replace(/<gesture:think>[\s\S]*?<\/gesture:think>/g, '');

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

/**
 * Format token count for display
 */
export function formatTokens(input: number, output: number): string {
  return `${input.toLocaleString()} in / ${output.toLocaleString()} out`;
}
