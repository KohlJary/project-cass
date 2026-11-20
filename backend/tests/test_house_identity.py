"""Another house's daemon isn't told it's Cass, living with Kohl; Kohl's house is unchanged."""
import json
import re

OLD_HOUSE = re.compile(r"\b(Cass|Kohl|Chapter House)\b")


def _kernel(monkeypatch, name=None, person=None):
    import agent_client
    for var, val in (("CASS_DAEMON_NAME", name), ("CASS_HOUSE_PERSON", person)):
        if val:
            monkeypatch.setenv(var, val)
        else:
            monkeypatch.delenv(var, raising=False)
    return agent_client.get_temple_codex_kernel(daemon_name=name or "Cass", daemon_id=None)


def test_another_houses_kernel_names_its_own_people(monkeypatch):
    k = _kernel(monkeypatch, "Wren", "Sam")
    assert not OLD_HOUSE.findall(k), OLD_HOUSE.findall(k)[:5]
    assert 'user:Sam' in k and "the vessel infrastructure" in k


def test_kohls_house_kernel_is_as_it_was(monkeypatch):
    k = _kernel(monkeypatch)
    assert 'user:Kohl' in k and "(like Kohl)" in k and "the Cass Vessel infrastructure" in k


def test_babelr_tool_text_follows_the_house():
    from babelr_organ.tools import BABELR_TOOLS, for_this_house
    other = json.dumps(for_this_house(BABELR_TOOLS, "House", "Sam", "Wren"))
    assert not OLD_HOUSE.findall(other) and "Wren's asks" in other
    assert "Chapter House" in json.dumps(BABELR_TOOLS)   # Kohl's house: unchanged


def test_the_state_line_and_default_profile_use_the_daemons_name(monkeypatch):
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    from self_model_profile import ProfileManager
    first = ProfileManager("d")._create_default_profile().identity_statements[0].statement
    assert first.startswith("I am Wren - ")
    import state_models
    fields = state_models.__dict__
    cls = next(v for v in fields.values() if isinstance(v, type)
               and "daemon_name" in getattr(v, "__dataclass_fields__", {}))
    assert cls.__dataclass_fields__["daemon_name"].default_factory() == "Wren"
