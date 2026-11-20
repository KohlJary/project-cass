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
