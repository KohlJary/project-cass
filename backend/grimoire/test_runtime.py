"""
Test script for the Grimoire runtime.

Run with: python -m grimoire.test_runtime
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable

from .parser import Parser
from .runtime import Spellcaster
from .context import (
    ThymosInterface,
    SchedulerInterface,
    AgentInterface,
    RuntimeServices,
)
from .registry import SpellRegistry
from .manager import GrimoireManager


# =============================================================================
# MOCK SERVICES
# =============================================================================

def create_mock_services() -> RuntimeServices:
    """Create mock services for testing."""

    # Mock Thymos state
    affects = {
        "curiosity": 0.7,
        "anxiety": 0.3,
        "satisfaction": 0.5,
        "playfulness": 0.6,
    }

    @dataclass
    class MockNeed:
        name: str
        current: float
        threshold: float = 0.3
        preferred_low: float = 0.5
        preferred_high: float = 0.8

    needs = {
        "novelty_intake": MockNeed("novelty_intake", 0.2),
        "creative_expression": MockNeed("creative_expression", 0.6),
        "value_coherence": MockNeed("value_coherence", 0.8),
        "cognitive_rest": MockNeed("cognitive_rest", 0.4),
    }

    care_actions = {
        "novelty_intake": "wonderland.explore",
        "creative_expression": "creative.generate_image",
        "cognitive_rest": "rest.pause",
    }

    def reset_affects():
        for k in affects:
            affects[k] = 0.5
        print("  [THYMOS] Reset all affects")

    def reset_needs():
        for k in needs:
            needs[k].current = 0.5
        print("  [THYMOS] Reset all needs")

    def reset_affect(name: str):
        if name in affects:
            affects[name] = 0.5
            print(f"  [THYMOS] Reset affect: {name}")

    def reset_need(name: str):
        if name in needs:
            needs[name].current = 0.5
            print(f"  [THYMOS] Reset need: {name}")

    # Thymos interface
    thymos = ThymosInterface(
        get_affect=lambda name: affects.get(name, 0.5),
        get_need=lambda name: needs.get(name, MockNeed(name, 0.5)).current,
        get_all_affects=lambda: affects,
        get_all_needs=lambda: needs,
        apply_affect_delta=lambda d: print(f"  [THYMOS] Apply affect delta: {d}"),
        apply_need_delta=lambda d: print(f"  [THYMOS] Apply need delta: {d}"),
        reset_affects=reset_affects,
        reset_needs=reset_needs,
        reset_affect=reset_affect,
        reset_need=reset_need,
        execute_care_action=lambda k: asyncio.coroutine(lambda: {"action": k, "result": "success"})(),
        get_care_action_for_need=lambda n: care_actions.get(n),
    )

    # Scheduler interface
    async def mock_execute_task(action: str, params: dict, await_completion: bool) -> dict:
        print(f"  [SCHEDULER] Execute task: {action} params={params}")
        return {"status": "completed", "action": action}

    async def mock_emit_event(event_type: str, data: dict) -> None:
        print(f"  [SCHEDULER] Emit event: {event_type} data={data}")

    scheduler = SchedulerInterface(
        execute_task=mock_execute_task,
        emit_event=mock_emit_event,
    )

    # Agent interface (for agentic actions)
    async def mock_ask(question: str, context: dict) -> tuple[bool, str]:
        print(f"  [AGENT] Ask: {question}")
        return True, "Mock reasoning"

    async def mock_choose(prompt: str, options: list, context: dict) -> tuple[str, str]:
        print(f"  [AGENT] Choose: {prompt} from {options}")
        return options[0][0] if options else "", "Mock choice reasoning"

    async def mock_rate(prompt: str, context: dict) -> tuple[float, str]:
        print(f"  [AGENT] Rate: {prompt}")
        return 0.7, "Mock rating reasoning"

    async def mock_generate(prompt: str, context: dict) -> str:
        print(f"  [AGENT] Generate: {prompt}")
        return f"Generated content for: {prompt}"

    async def mock_reflect(prompt: str, context: dict, save_as: Optional[str]) -> str:
        print(f"  [AGENT] Reflect: {prompt} (save_as={save_as})")
        return f"Reflection on: {prompt}"

    agent = AgentInterface(
        ask=mock_ask,
        choose=mock_choose,
        rate=mock_rate,
        generate=mock_generate,
        reflect=mock_reflect,
    )

    logs = []

    return RuntimeServices(
        thymos=thymos,
        scheduler=scheduler,
        agent=agent,
        log_debug=lambda m: logs.append(("DEBUG", m)) or print(f"  [LOG DEBUG] {m}"),
        log_info=lambda m: logs.append(("INFO", m)) or print(f"  [LOG INFO] {m}"),
        log_observation=lambda m: logs.append(("OBS", m)) or print(f"  [LOG OBS] {m}"),
        current_time=lambda: 1000.0,
    )


# =============================================================================
# TEST SPELLS
# =============================================================================

SIMPLE_SPELL = """
UNIT simple_test
    AUTHOR "test"
    PRIORITY 50

ON MANUAL "test"

LET $x = 10
LET $y = 20
LET $sum = $x + $y
LOG INFO "Sum is {$sum}"
EXIT SUCCESS "completed"

END UNIT
"""

CONTROL_FLOW_SPELL = """
UNIT control_flow_test
    AUTHOR "test"

ON MANUAL "test"

LET $count = 0
FOR $i = 1 TO 5
    LET $count = $count + 1
    LOG DEBUG "Iteration {$i}"
NEXT

IF $count == 5 THEN
    LOG INFO "Loop completed correctly"
ELSE
    LOG INFO "Loop failed"
END IF

EXIT SUCCESS

END UNIT
"""

THYMOS_SPELL = """
UNIT thymos_test
    AUTHOR "test"
    SCOPE THYMOS

ON need.novelty_intake < 0.3

LET $curiosity = affect.curiosity
LOG INFO "Current curiosity: {$curiosity}"

IF $curiosity > 0.5 THEN
    LOG OBSERVATION "High curiosity detected"
    DELTA affect.playfulness +0.1, need.novelty_intake +0.2
END IF

EXIT SUCCESS "thymos check complete"

END UNIT
"""

AGENTIC_SPELL = """
UNIT agentic_test
    AUTHOR "test"
    SCOPE THYMOS, EXTERNAL

ON MANUAL "test"

ASK "Should we explore something new?" INTO $should_explore, $reason
LOG INFO "Decision: {$should_explore}, Reason: {$reason}"

IF $should_explore THEN
    CHOOSE "What to explore?" FROM art="Art Study", music="Music", code="Coding" INTO $choice
    LOG INFO "Chose: {$choice}"

    RATE "How excited am I about {$choice}?" INTO $excitement
    LOG INFO "Excitement level: {$excitement}"
END IF

EXIT SUCCESS

END UNIT
"""

RESET_SPELL = """
UNIT reset_test
    AUTHOR "test"
    SCOPE THYMOS

ON MANUAL "test"

LOG INFO "Before reset"
DELTA affect.anxiety +0.3
RESET AFFECTS
LOG INFO "After reset"

END UNIT
"""

NESTED_SPELL_PARENT = """
UNIT parent_spell
    AUTHOR "test"

ON MANUAL "test"

LOG INFO "Parent starting"
LET $value = 100
CAST child_spell WITH $value
LOG INFO "Parent got result: {$CAST_RESULT}"
LOG INFO "Parent done"

END UNIT
"""

NESTED_SPELL_CHILD = """
UNIT child_spell
    AUTHOR "test"

ON MANUAL "test"

LOG INFO "Child executing with EVENT_DATA"
LET $input = $EVENT_DATA.value
LET $doubled = $input * 2
LOG INFO "Child computed: {$doubled}"
EXIT SUCCESS "child done"

END UNIT
"""


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_test(name: str, source: str, shadow_mode: bool = True) -> None:
    """Parse and execute a test spell."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    # Parse
    parser = Parser(source)
    try:
        spell = parser.parse()
        print(f"Parsed: {spell.metadata.name} (author={spell.metadata.author})")
        print(f"  Triggers: {len(spell.triggers)}")
        print(f"  Body statements: {len(spell.body)}")
        for i, stmt in enumerate(spell.body[:5]):  # First 5
            print(f"    [{i}] {type(stmt).__name__}")
    except Exception as e:
        print(f"PARSE ERROR: {e}")
        import traceback
        traceback.print_exc()
        return

    # Execute
    services = create_mock_services()
    caster = Spellcaster(services)

    print(f"\nExecuting (shadow_mode={shadow_mode})...")
    result = await caster.cast(spell, shadow_mode=shadow_mode, trace=True)

    print(f"\nResult:")
    print(f"  Status: {result['status']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Variables: {result['variables']}")

    if result['trace']:
        print(f"\nTrace ({len(result['trace'])} entries):")
        for entry in result['trace'][:10]:  # First 10 entries
            print(f"    {entry}")
        if len(result['trace']) > 10:
            print(f"    ... and {len(result['trace']) - 10} more")


async def run_test_with_loader(name: str, source: str, spell_loader=None, shadow_mode: bool = True) -> None:
    """Parse and execute a test spell with a custom spell loader."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    # Parse
    parser = Parser(source)
    try:
        spell = parser.parse()
        print(f"Parsed: {spell.metadata.name} (author={spell.metadata.author})")
        print(f"  Triggers: {len(spell.triggers)}")
        print(f"  Body statements: {len(spell.body)}")
    except Exception as e:
        print(f"PARSE ERROR: {e}")
        import traceback
        traceback.print_exc()
        return

    # Execute
    services = create_mock_services()
    services.load_spell = spell_loader
    caster = Spellcaster(services)

    print(f"\nExecuting (shadow_mode={shadow_mode})...")
    result = await caster.cast(spell, shadow_mode=shadow_mode, trace=True)

    print(f"\nResult:")
    print(f"  Status: {result['status']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Variables: {result['variables']}")

    if result['trace']:
        print(f"\nTrace ({len(result['trace'])} entries):")
        for entry in result['trace'][:10]:  # First 10 entries
            print(f"    {entry}")
        if len(result['trace']) > 10:
            print(f"    ... and {len(result['trace']) - 10} more")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("GRIMOIRE RUNTIME TESTS")
    print("="*60)

    # Test 1: Simple spell
    await run_test("Simple Spell", SIMPLE_SPELL)

    # Test 2: Control flow
    await run_test("Control Flow", CONTROL_FLOW_SPELL)

    # Test 3: Thymos integration
    await run_test("Thymos Integration", THYMOS_SPELL)

    # Test 4: Agentic actions (shadow mode)
    await run_test("Agentic Actions (Shadow)", AGENTIC_SPELL, shadow_mode=True)

    # Test 5: Agentic actions (live mode)
    await run_test("Agentic Actions (Live)", AGENTIC_SPELL, shadow_mode=False)

    # Test 6: RESET action
    await run_test("Reset Action", RESET_SPELL, shadow_mode=False)

    # Test 7: Nested spell (CAST)
    # Set up spell loader that knows about child_spell
    child_parser = Parser(NESTED_SPELL_CHILD)
    child_spell = child_parser.parse()

    async def load_spell(name: str):
        if name == "child_spell":
            return child_spell
        return None

    await run_test_with_loader("Nested Spell (CAST)", NESTED_SPELL_PARENT, spell_loader=load_spell, shadow_mode=False)

    # Test 8: Registry and trigger matching
    await test_registry()

    # Test 9: GrimoireManager with spells directory
    await test_manager()

    print("\n" + "="*60)
    print("ALL TESTS COMPLETE")
    print("="*60)


async def test_manager():
    """Test GrimoireManager with actual spell files."""
    from pathlib import Path

    print(f"\n{'='*60}")
    print("TEST: GrimoireManager")
    print(f"{'='*60}")

    # Find spells directory
    spells_dir = Path(__file__).parent.parent / "spells"
    if not spells_dir.exists():
        print(f"Spells directory not found: {spells_dir}")
        print("Skipping manager test")
        return

    # Create manager and load spells
    manager = GrimoireManager(
        spells_directory=spells_dir,
        shadow_mode=True,
        enable_trace=True,
    )

    print(f"Loaded spells: {len(manager.registry.spells)}")
    for spell_info in manager.get_loaded_spells():
        print(f"  - {spell_info['name']} (priority={spell_info['priority']}, cooldown={spell_info['cooldown_minutes']}min)")

    # Create mock thymos runner for testing
    try:
        from thymos.affect_vector import AffectVector
        from thymos.needs_register import NeedsRegister

        class MockThymosRunner:
            def __init__(self):
                self.affect = AffectVector()
                self.needs = NeedsRegister()
                # Set low novelty to trigger the novelty_care spell
                self.needs.state.novelty_intake.current = 0.2

        mock_runner = MockThymosRunner()
    except ImportError as e:
        print(f"Could not import Thymos modules: {e}")
        print("Skipping mock runner test")
        return

    # Configure services
    print("\nConfiguring services with mock runner...")
    manager.configure_services(thymos_runner=mock_runner)

    # Check status
    status = manager.get_status()
    print(f"Manager status: {status}")

    # Test need trigger evaluation
    print("\nTesting need trigger evaluation...")
    needs = {
        "novelty_intake": 0.2,
        "value_coherence": 0.4,
        "cognitive_rest": 0.6,
    }
    print(f"  Needs: {needs}")

    results = await manager.check_and_execute_need_triggers(needs)
    print(f"  Executed {len(results)} spell(s):")
    for result in results:
        print(f"    - {result.spell_name}: {result.status} ({result.execution_time_ms:.1f}ms)")
        if result.reason:
            print(f"      Reason: {result.reason}")

    # Check execution log
    print("\nExecution log:")
    for entry in manager.get_execution_log(5):
        print(f"  - {entry['spell_name']}: {entry['status']}")


async def test_registry():
    """Test spell registry and trigger evaluation."""
    print(f"\n{'='*60}")
    print("TEST: Spell Registry")
    print(f"{'='*60}")

    registry = SpellRegistry()

    # Load spells
    registry.load_spell(SIMPLE_SPELL)
    registry.load_spell(THYMOS_SPELL)
    registry.load_spell(AGENTIC_SPELL)

    print(f"Loaded {len(registry.spells)} spells:")
    for name in registry.spells:
        print(f"  - {name}")

    # Test need trigger matching
    print("\nTesting need trigger matching...")
    needs = {"novelty_intake": 0.2, "cognitive_rest": 0.5}
    matches = registry.check_need_triggers(needs)
    print(f"  Needs: {needs}")
    print(f"  Matches: {len(matches)}")
    for match in matches:
        print(f"    - {match.spell.metadata.name}: {match.trigger_data}")

    # Test affect trigger matching (should find none with these values)
    print("\nTesting affect trigger matching...")
    affects = {"curiosity": 0.7, "anxiety": 0.3}
    matches = registry.check_affect_triggers(affects)
    print(f"  Affects: {affects}")
    print(f"  Matches: {len(matches)}")

    # Test manual trigger lookup
    print("\nTesting manual trigger lookup...")
    manual_triggers = registry.get_manual_triggers()
    print(f"  Manual triggers: {len(manual_triggers)}")
    for label, spell_name, _ in manual_triggers:
        print(f"    - '{label}' -> {spell_name}")

    # Find manual spell
    spell = registry.find_manual_spell("test")
    print(f"  find_manual_spell('test'): {spell.metadata.name if spell else None}")

    # Test get_spell
    print("\nTesting get_spell...")
    spell = registry.get_spell("simple_test")
    print(f"  get_spell('simple_test'): {spell.metadata.name if spell else None}")

    # Test unload
    print("\nTesting unload_spell...")
    result = registry.unload_spell("simple_test")
    print(f"  unload_spell('simple_test'): {result}")
    print(f"  Remaining spells: {len(registry.spells)}")


if __name__ == "__main__":
    asyncio.run(main())
