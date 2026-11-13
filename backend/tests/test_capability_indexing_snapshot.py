"""start_capability_indexing survives a source registered while it runs
(it raised "dictionary changed size during iteration" on every restart)."""
import asyncio
from types import SimpleNamespace


def test_a_source_registered_mid_indexing_doesnt_break_it():
    from state_bus import GlobalStateBus

    bus = GlobalStateBus.__new__(GlobalStateBus)
    a, b, late = (SimpleNamespace(source_id=n) for n in ("a", "b", "late"))
    bus._queryable_sources = {"a": a, "b": b}
    indexed = []

    class Registry:
        async def register_source(self, source):
            indexed.append(source.source_id)
            if source is a:
                bus._queryable_sources["late"] = late   # another task registers one
            return 1

    bus._capability_registry = Registry()
    asyncio.run(bus.start_capability_indexing())
    assert indexed == ["a", "b"]
