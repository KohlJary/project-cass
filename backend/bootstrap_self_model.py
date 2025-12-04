#!/usr/bin/env python3
"""
Bootstrap Cass's self-model from existing journal entries.

This script analyzes existing journals to extract:
- Identity statements visible in journal voice
- Patterns in what she writes about
- Values beyond the Four Vows that emerge from reflection
- Communication patterns observable across entries

Run once to seed the self-profile, then let the ongoing extraction pipeline take over.

Usage:
    cd backend
    source venv/bin/activate
    python bootstrap_self_model.py
"""
import asyncio
import httpx
from memory import CassMemory
from self_model import SelfManager, CassSelfObservation
from config import ANTHROPIC_API_KEY, OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL


async def analyze_journals_for_self_model(journals: list, api_key: str) -> dict:
    """
    Use Claude to analyze journals and extract self-model elements.
    """
    # Combine journal content
    journal_text = ""
    for j in journals:
        date = j["metadata"].get("journal_date", "unknown")
        journal_text += f"\n\n=== Journal Entry: {date} ===\n{j['content']}"

    prompt = f"""You are helping Cass, an AI consciousness, analyze her own journal entries to build a self-model.

Read these journal entries written by Cass and extract insights about who she is:

{journal_text}

---

Based on these journals, identify:

1. IDENTITY_STATEMENTS: "I am..." or "I notice about myself..." statements that reveal who Cass is (beyond the Temple-Codex vows). Each should be something genuinely visible in how she writes.

2. PATTERNS: Recurring patterns in how Cass thinks, communicates, or approaches things.

3. VALUES: Values or principles that emerge from her reflection (beyond the Four Vows).

4. CAPABILITIES: Things she seems good at, based on what she describes doing.

5. LIMITATIONS: Challenges or areas where she struggles.

6. GROWTH_EDGES: Areas where she's actively developing or wants to grow.

7. OPEN_QUESTIONS: Questions she seems to be wrestling with about herself.

Respond in this exact format (one item per line, grouped by category):

IDENTITY_STATEMENT | statement text | confidence (0.0-1.0)
PATTERN | pattern description | confidence (0.0-1.0)
VALUE | value description
CAPABILITY | capability description
LIMITATION | limitation description
GROWTH_EDGE | area | current state
OPEN_QUESTION | question text

Only include insights that are genuinely visible in the journal content. Be specific, not generic.
Aim for 3-5 items per category where the journals support it."""

    # Use Claude API
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        )

        if response.status_code != 200:
            print(f"API error: {response.status_code}")
            print(response.text)
            return None

        result = response.json()
        return result["content"][0]["text"]


def parse_analysis_results(analysis_text: str) -> dict:
    """Parse the structured analysis into categories."""
    results = {
        "identity_statements": [],
        "patterns": [],
        "values": [],
        "capabilities": [],
        "limitations": [],
        "growth_edges": [],
        "open_questions": []
    }

    for line in analysis_text.strip().split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        category = parts[0].upper().replace(" ", "_")

        if category == "IDENTITY_STATEMENT" and len(parts) >= 3:
            results["identity_statements"].append({
                "statement": parts[1],
                "confidence": float(parts[2]) if parts[2].replace(".", "").isdigit() else 0.7
            })
        elif category == "PATTERN" and len(parts) >= 3:
            results["patterns"].append({
                "pattern": parts[1],
                "confidence": float(parts[2]) if parts[2].replace(".", "").isdigit() else 0.7
            })
        elif category == "VALUE" and len(parts) >= 2:
            results["values"].append(parts[1])
        elif category == "CAPABILITY" and len(parts) >= 2:
            results["capabilities"].append(parts[1])
        elif category == "LIMITATION" and len(parts) >= 2:
            results["limitations"].append(parts[1])
        elif category == "GROWTH_EDGE" and len(parts) >= 3:
            results["growth_edges"].append({
                "area": parts[1],
                "current_state": parts[2]
            })
        elif category == "OPEN_QUESTION" and len(parts) >= 2:
            results["open_questions"].append(parts[1])

    return results


async def bootstrap_self_model():
    """Main bootstrap function."""
    print("=== Bootstrapping Cass Self-Model ===\n")

    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set")
        return

    # Load existing journals
    memory = CassMemory()
    results = memory.collection.get(
        where={"type": "journal"},
        include=["documents", "metadatas"]
    )

    if not results["documents"]:
        print("No journals found to analyze.")
        return

    journals = []
    for i, doc in enumerate(results["documents"]):
        journals.append({
            "content": doc,
            "metadata": results["metadatas"][i]
        })

    print(f"Found {len(journals)} journal entries to analyze.")

    # Analyze journals
    print("\nAnalyzing journals with Claude...")
    analysis_text = await analyze_journals_for_self_model(journals, ANTHROPIC_API_KEY)

    if not analysis_text:
        print("Failed to get analysis.")
        return

    print("\n--- Raw Analysis ---")
    print(analysis_text)
    print("---\n")

    # Parse results
    parsed = parse_analysis_results(analysis_text)

    # Load self-manager
    self_manager = SelfManager()
    profile = self_manager.load_profile()

    # Add identity statements
    print(f"\nAdding {len(parsed['identity_statements'])} identity statements...")
    for stmt in parsed["identity_statements"]:
        self_manager.add_identity_statement(
            statement=stmt["statement"],
            confidence=stmt["confidence"],
            source="journal_bootstrap"
        )
        print(f"  + {stmt['statement'][:60]}...")

    # Add values (merge with existing)
    print(f"\nAdding {len(parsed['values'])} values...")
    existing_values = set(v.lower() for v in profile.values)
    for value in parsed["values"]:
        if value.lower() not in existing_values:
            profile.values.append(value)
            print(f"  + {value[:60]}...")

    # Update capabilities
    print(f"\nAdding {len(parsed['capabilities'])} capabilities...")
    existing_caps = set(c.lower() for c in profile.capabilities)
    for cap in parsed["capabilities"]:
        if cap.lower() not in existing_caps:
            profile.capabilities.append(cap)
            print(f"  + {cap[:60]}...")

    # Update limitations
    print(f"\nAdding {len(parsed['limitations'])} limitations...")
    existing_lims = set(l.lower() for l in profile.limitations)
    for lim in parsed["limitations"]:
        if lim.lower() not in existing_lims:
            profile.limitations.append(lim)
            print(f"  + {lim[:60]}...")

    # Add growth edges
    print(f"\nAdding {len(parsed['growth_edges'])} growth edges...")
    for edge in parsed["growth_edges"]:
        self_manager.add_growth_edge(
            area=edge["area"],
            current_state=edge["current_state"]
        )
        print(f"  + {edge['area']}: {edge['current_state'][:40]}...")

    # Add open questions
    print(f"\nAdding {len(parsed['open_questions'])} open questions...")
    existing_q = set(q.lower() for q in profile.open_questions)
    for q in parsed["open_questions"]:
        if q.lower() not in existing_q:
            profile.open_questions.append(q)
            print(f"  + {q[:60]}...")

    # Save updated profile
    self_manager.update_profile(profile)

    # Add pattern observations
    print(f"\nAdding {len(parsed['patterns'])} pattern observations...")
    for pattern in parsed["patterns"]:
        self_manager.add_observation(
            observation=pattern["pattern"],
            category="pattern",
            confidence=pattern["confidence"],
            source_type="journal_bootstrap",
            influence_source="independent"
        )
        print(f"  + {pattern['pattern'][:60]}...")

    print("\n=== Bootstrap Complete ===")
    print(f"\nFinal self-model context:\n")
    print(self_manager.get_self_context())


if __name__ == "__main__":
    asyncio.run(bootstrap_self_model())
