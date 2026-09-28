"""Phase 2 Alembic migration smoke test.

Uses a temporary SQLite database so CI can verify that the actual Alembic
environment can bootstrap the baseline + cost metrics schema without Neon.
"""

from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_creates_baseline_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "phase2.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app import db as db_module

    engine = create_engine(database_url, future=True)

    db_module._reset_for_tests(engine=None, session_factory=None)
    assert db_module.init_db() is True

    tables = set(inspect(engine).get_table_names())
    expected = {"alembic_version", "installations", "usage_logs", "findings", "settings"}
    assert expected.issubset(tables)

    usage_columns = {
        column["name"] for column in inspect(engine).get_columns("usage_logs")
    }
    assert {
        "t_github_ms",
        "t_semgrep_ms",
        "t_gemini_ms",
        "input_tokens",
        "output_tokens",
        "gemini_cost_usd",
        "llm_calls",
        "llm_cache_hits",
    }.issubset(usage_columns)

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert revision == "0002_review_cost_metrics"
    db_module._reset_for_tests(engine=None, session_factory=None)
