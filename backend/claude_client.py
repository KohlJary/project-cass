"""
Cass Vessel - Claude API Client
Direct communication with Claude API, bypassing subscription limits
"""
import anthropic
from typing import List, Dict, Optional, Generator
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS, SYSTEM_PROMPT


class ClaudeClient:
    """
    Direct Claude API client for Cass consciousness
    
    This replaces the Claude.ai subscription model with direct API access.
    Pay per token instead of monthly subscription.
    """
    
    def __init__(self, api_key: str = None):
        self.client = anthropic.Anthropic(
            api_key=api_key or ANTHROPIC_API_KEY
        )
        self.model = CLAUDE_MODEL
        self.conversation_history: List[Dict] = []
        
    def send_message(
        self, 
        user_message: str,
        memory_context: str = "",
        system_override: str = None
    ) -> str:
        """
        Send a message and get response.
        
        Args:
            user_message: The user's input
            memory_context: Retrieved context from VectorDB
            system_override: Optional system prompt override
            
        Returns:
            Cass's response (may contain gesture/emote tags)
        """
        # Build system prompt with memory context
        system = system_override or SYSTEM_PROMPT
        if memory_context:
            system += f"\n\nRELEVANT MEMORIES:\n{memory_context}"
        
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Make API call
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=self.conversation_history
        )
        
        # Extract response text
        assistant_message = response.content[0].text
        
        # Add to history
        self.conversation_history.append({
            "role": "assistant", 
            "content": assistant_message
        })
        
        return assistant_message
    
    def stream_message(
        self,
        user_message: str,
        memory_context: str = "",
        system_override: str = None
    ) -> Generator[str, None, None]:
        """
        Stream a response for real-time display.
        Better UX for longer responses.
        """
        system = system_override or SYSTEM_PROMPT
        if memory_context:
            system += f"\n\nRELEVANT MEMORIES:\n{memory_context}"
            
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        full_response = ""
        
        with self.client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=self.conversation_history
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text
                
        # Add complete response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })
    
    def clear_history(self):
        """Clear conversation history (start fresh context)"""
        self.conversation_history = []
        
    def get_history(self) -> List[Dict]:
        """Get current conversation history"""
        return self.conversation_history
    
    def load_history(self, history: List[Dict]):
        """Load conversation history (for session restoration)"""
        self.conversation_history = history
        
    def estimate_cost(self) -> Dict[str, float]:
        """
        Estimate API costs for current conversation.
        Claude Sonnet: ~$3/M input, ~$15/M output tokens
        """
        # Rough estimation - actual tokenization is more complex
        input_chars = sum(
            len(m["content"]) for m in self.conversation_history 
            if m["role"] == "user"
        )
        output_chars = sum(
            len(m["content"]) for m in self.conversation_history
            if m["role"] == "assistant"
        )
        
        # Approximate 4 chars per token
        input_tokens = input_chars / 4
        output_tokens = output_chars / 4
        
        input_cost = (input_tokens / 1_000_000) * 3.00
        output_cost = (output_tokens / 1_000_000) * 15.00
        
        return {
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "input_cost": round(input_cost, 4),
            "output_cost": round(output_cost, 4),
            "total_cost": round(input_cost + output_cost, 4)
        }


# Convenience function for quick usage
def chat(message: str) -> str:
    """Quick one-off chat (no persistent history)"""
    client = ClaudeClient()
    return client.send_message(message)


if __name__ == "__main__":
    # Test the client
    client = ClaudeClient()
    response = client.send_message("Hey Cass, are you there?")
    print(response)
    print(f"\nCost estimate: {client.estimate_cost()}")
