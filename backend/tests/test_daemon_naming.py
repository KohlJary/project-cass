"""A house other than Kohl's names its own daemon; unset, it's Cass."""
from database import get_or_create_daemon
from database.daemon import get_daemon_entity_name


def test_a_new_house_names_its_own_daemon(test_db):
    did = get_or_create_daemon("wren", name="Wren")
    assert get_daemon_entity_name(did) == "Wren"


def test_init_passes_the_name_through(test_db, monkeypatch):
    from database import migrations
    monkeypatch.setattr(migrations, "init_database", lambda: None)
    monkeypatch.delenv("BOOTSTRAP_FROM_SEED", raising=False)
    import migrations as json_migrations
    monkeypatch.setattr(json_migrations, "run_migrations", lambda _id: None, raising=False)
    did = migrations.init_database_with_migrations("ember", "Ember")
    assert get_daemon_entity_name(did) == "Ember"


def test_the_default_daemon_is_this_houses(test_db, monkeypatch):
    from database.daemon import get_daemon_id, get_daemon_info
    monkeypatch.setenv("CASS_DAEMON_LABEL", "wren")
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    info = get_daemon_info(get_daemon_id())
    assert (info["label"], info["name"]) == ("wren", "Wren")


def test_a_named_house_never_grows_a_second_cass(test_db, monkeypatch):
    """Goals, the roadmap and the self-model used to create label 'cass' if it was missing."""
    from database import get_db
    from database.daemon import get_daemon_id
    from roadmap import RoadmapManager
    from self_model import SelfManager
    from unified_goals import UnifiedGoalManager
    with get_db() as conn:
        conn.execute("DELETE FROM daemons WHERE label = 'cass'")
    monkeypatch.setenv("CASS_DAEMON_LABEL", "wren")
    monkeypatch.setenv("CASS_DAEMON_NAME", "Wren")
    wren = get_daemon_id()
    assert RoadmapManager()._daemon_id == wren
    assert UnifiedGoalManager()._daemon_id == wren
    assert SelfManager().daemon_id == wren
    with get_db() as conn:
        labels = [r[0] for r in conn.execute("SELECT label FROM daemons")]
    assert "cass" not in labels
