"""estimate_cost bills calls the way Anthropic does (RoboKohl, 2026-11-24)."""
from token_tracker import estimate_cost


def test_haiku_4_5_is_one_and_five_dollars():
    assert estimate_cost("anthropic", "claude-haiku-4-5-20251001", 1_000_000, 0) == 1.0
    assert estimate_cost("anthropic", "claude-haiku-4-5-20251001", 0, 1_000_000) == 5.0


def test_cache_writes_are_charged_and_reads_counted_once():
    # Ledger convention: input includes reads. 100 uncached + 50k read, 10k written, 500 out.
    got = estimate_cost("anthropic", "claude-haiku-4-5-20251001", 50_100, 500,
                        cache_read_tokens=50_000, cache_write_tokens=10_000)
    raw = estimate_cost("anthropic", "claude-haiku-4-5-20251001", 100, 500, cache_read_tokens=50_000,
                        cache_write_tokens=10_000, input_includes_cache_reads=False)
    assert got == raw
    want = (100 * 1.0 + 10_000 * 1.25 + 50_000 * 0.1 + 500 * 5.0) / 1_000_000
    assert abs(got - want) < 1e-9
    assert got > 0  # never negative on a cache-heavy call


def test_a_model_with_its_own_cache_read_price():
    got = estimate_cost("anthropic", "claude-sonnet-5-5", 0, 0, cache_read_tokens=1_000_000)
    assert abs(got - 0.10) < 1e-9


def test_dated_variants_and_unknowns():
    assert estimate_cost("anthropic", "claude-sonnet-4-6-20260101", 1_000_000, 0) == 3.0
    assert estimate_cost("anthropic", "no-such-model", 1, 1) is None
    assert estimate_cost("ollama", "qwen3:14b", 1000, 1000) is None
