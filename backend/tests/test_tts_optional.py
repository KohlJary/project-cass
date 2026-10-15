"""
TTS is optional: a missing piper-tts or pydub must not stop the server booting
(card 01: "tts.py imports piper/pydub unguarded").

Each check runs in a fresh interpreter with piper and pydub made unimportable,
so it doesn't depend on (or disturb) what this environment has installed.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# Setting sys.modules[name] = None makes `import name` raise ImportError.
BLOCK_TTS_DEPS = """
import sys
for name in ("piper", "piper.config", "pydub"):
    sys.modules[name] = None
"""


def _run(code, timeout=55):
    env = dict(os.environ)
    env.setdefault("CASS_PROFILE", "test")
    result = subprocess.run(
        [sys.executable, "-c", BLOCK_TTS_DEPS + textwrap.dedent(code)],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=timeout,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-4000:]
    return result.stdout


def test_tts_module_imports_without_piper_or_pydub():
    out = _run("""
        import tts
        assert tts.PIPER_AVAILABLE is False and tts.PYDUB_AVAILABLE is False
        assert tts.is_available() is False
        assert "piper" not in tts.get_available_providers()
        # Pure-text helpers still work
        assert tts.clean_text_for_tts("**hi**") == "hi"
        try:
            tts.synthesize("hello")
        except tts.TTSUnavailable:
            print("UNAVAILABLE")
    """)
    assert "UNAVAILABLE" in out


@pytest.mark.timeout(120)
def test_server_module_imports_without_piper_or_pydub():
    """main_sdk imports tts at module level; that used to kill the boot."""
    pytest.importorskip("anthropic")  # main_sdk needs the runtime deps
    out = _run("""
        import main_sdk
        print("BOOTED", main_sdk.app is not None)
    """, timeout=110)
    assert "BOOTED True" in out


def test_tts_availability_respects_lever(levers):
    """With the deps present, the "tts" lever still decides availability."""
    tts = pytest.importorskip("tts")
    if not tts.PIPER_AVAILABLE:
        pytest.skip("piper not installed here")
    with levers(tts=True):
        assert tts.is_available() is True
    with levers(tts=False):
        assert tts.is_available() is False
