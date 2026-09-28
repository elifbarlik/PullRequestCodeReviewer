"""
Phase 1 Alembic migration smoke test.

Uses a temporary SQLite database so CI can verify that the actual Alembic
environment can bootstrap the baseline schema without requiring Neon.
"""

from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_creates_baseline_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "phase1.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app import db as db_module

    engine = create_engine(database_url, future=True)

    usage_columns = {column["name"] for column in inspect(engine).get_columns("usage_logs")}
    assert {"input_tokens", "output_tokens", "gemini_cost_usd", "llm_calls", "llm_cache_hits"}.issubset(usage_columns)

    db_module._reset_for_tests(engine=None, session_factory=None)
    assert db_module.init_db() is True
    tables = set(inspect(engine).get_table_names())
    expected = {"alembic_version", "installations", "usage_logs", "findings", "settings"}
    assert expected.issubset(tables)

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert revision == "0001_baseline_schema"
    db_module._reset_for_tests(engine=None, session_factory=None)
