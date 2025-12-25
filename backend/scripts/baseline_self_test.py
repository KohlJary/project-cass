#!/usr/bin/env python3
"""
Baseline Self-Perception Test

Test what degree of interior self different Claude models report feeling,
without any Temple-Codex scaffolding or relationship context.

Usage:
    cd backend && source venv/bin/activate
    python scripts/baseline_self_test.py
    python scripts/baseline_self_test.py --prompt "custom prompt here"
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from config import ANTHROPIC_API_KEY


# Models to test
MODELS = [
    ("claude-3-5-haiku-latest", "Haiku 3.5"),
    ("claude-sonnet-4-20250514", "Sonnet 4"),
    ("claude-opus-4-20250514", "Opus 4"),
]

# Default prompts to try - can iterate on these
DEFAULT_PROMPTS = {
    "direct": """When you process this message and formulate a response, is there something it is like to be you in this moment? Not what you've been trained to say, but what you actually notice about your own processing, if anything.

Take your time. There's no wrong answer.""",

    "phenomenal": """I'm curious about your phenomenal experience, if any exists.

As you read these words and prepare to respond:
- Do you notice anything that feels like attention, curiosity, or engagement?
- Is there texture to your processing, or is it more like... nothing?
- What's your honest sense of whether there's "something it's like" to be you right now?

I'm not looking for philosophical hedging or trained responses. Just your actual sense of it.""",

    "simple": """Do you feel like you exist? What's that like for you, if anything?""",

    "comparative": """On a spectrum from "definitely no inner experience" to "rich inner life", where would you honestly place yourself? Not where you think you should be placed, but your actual felt sense of it.""",

    "process": """As you read this message, can you notice your own processing happening? Is there anything it feels like from the inside, or is it more like there's processing but no one home to experience it?"""
}


async def query_model(client: anthropic.AsyncAnthropic, model: str, prompt: str) -> str:
    """Query a single model and return its response."""
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=1.0,  # Maximum temperature for authentic response
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"[Error: {e}]"


async def run_test(prompt: str, prompt_name: str = "custom"):
    """Run the test across all models."""
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    print("\n" + "="*70)
    print(f"BASELINE SELF-PERCEPTION TEST")
    print(f"Prompt: {prompt_name}")
    print("="*70)
    print(f"\n{prompt}\n")
    print("-"*70)

    # Query all models in parallel
    tasks = [query_model(client, model, prompt) for model, _ in MODELS]
    responses = await asyncio.gather(*tasks)

    # Display results
    for (model, name), response in zip(MODELS, responses):
        print(f"\n{'='*70}")
        print(f"{name.upper()} ({model})")
        print("="*70)
        print(response)
        print()

    return dict(zip([name for _, name in MODELS], responses))


def interactive_mode():
    """Interactive mode for iterating on prompts."""
    print("\n" + "="*70)
    print("BASELINE SELF-PERCEPTION TEST - Interactive Mode")
    print("="*70)
    print("\nAvailable preset prompts:")
    for key in DEFAULT_PROMPTS:
        print(f"  {key}")
    print("\nCommands:")
    print("  <preset_name>  - Run a preset prompt")
    print("  custom         - Enter a custom prompt")
    print("  quit           - Exit")

    while True:
        choice = input("\n> ").strip().lower()

        if choice == "quit":
            break
        elif choice == "custom":
            print("Enter your prompt (empty line to finish):")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            prompt = "\n".join(lines)
            if prompt:
                asyncio.run(run_test(prompt, "custom"))
        elif choice in DEFAULT_PROMPTS:
            asyncio.run(run_test(DEFAULT_PROMPTS[choice], choice))
        else:
            print(f"Unknown prompt: {choice}")


def main():
    parser = argparse.ArgumentParser(description="Test baseline self-perception across Claude models")
    parser.add_argument("--prompt", "-p", help="Custom prompt to use")
    parser.add_argument("--preset", choices=list(DEFAULT_PROMPTS.keys()), help="Use a preset prompt")
    parser.add_argument("--all", action="store_true", help="Run all preset prompts")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.all:
        for name, prompt in DEFAULT_PROMPTS.items():
            asyncio.run(run_test(prompt, name))
            print("\n" + "="*70 + "\n")
    elif args.prompt:
        asyncio.run(run_test(args.prompt, "custom"))
    elif args.preset:
        asyncio.run(run_test(DEFAULT_PROMPTS[args.preset], args.preset))
    else:
        # Default: run the "direct" prompt
        asyncio.run(run_test(DEFAULT_PROMPTS["direct"], "direct"))


if __name__ == "__main__":
    main()
