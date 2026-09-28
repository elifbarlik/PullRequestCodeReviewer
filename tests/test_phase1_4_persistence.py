import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import sessionmaker

from app.db import _reset_for_tests
from app.models import Base, Installation, Repository, ReviewRun, WebhookDelivery
from app.repository import (
    claim_webhook_delivery,
    create_review_run,
    mark_webhook_delivery,
    update_review_run,
    upsert_repository,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    _reset_for_tests(engine=engine, session_factory=Session)
    with Session() as session:
        session.add(
            Installation(
                id=100,
                account_login="test-org",
                account_type="Organization",
                is_active=True,
            )
        )
        session.commit()
    yield engine
    _reset_for_tests()


def test_webhook_delivery_is_durable_and_idempotent(db):
    assert claim_webhook_delivery("delivery-1", "pull_request", "opened", 100, None) is False
    assert claim_webhook_delivery("delivery-1", "pull_request", "opened", 100, None) is True

    mark_webhook_delivery("delivery-1", "processed")

    Session = sessionmaker(bind=db, future=True)
    with Session() as session:
        row = session.scalar(
            select(WebhookDelivery).where(WebhookDelivery.delivery_id == "delivery-1")
        )
        assert row.status == "processed"
        assert row.processed_at is not None


def test_review_run_has_persistent_lifecycle(db):
    repository_id = upsert_repository(
        installation_id=100,
        github_repository_id=200,
        owner="test-org",
        name="repo",
        full_name="test-org/repo",
    )
    assert repository_id == 200

    run_id = create_review_run(100, repository_id, 42, "abc123")
    assert run_id is not None
    assert create_review_run(100, repository_id, 42, "abc123") == run_id

    update_review_run(run_id, "running", files_scanned=3)
    update_review_run(run_id, "completed", findings_count=2)

    Session = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(bind=db, future=True)
    with Session() as session:
        row = session.scalar(select(ReviewRun).where(ReviewRun.id == run_id))
        assert row.status == "completed"
        assert row.started_at is not None
        assert row.completed_at is not None
        assert row.files_scanned == 3
        assert row.findings_count == 2


def test_repository_upsert_is_idempotent(db):
    upsert_repository(100, 200, "test-org", "repo", "test-org/repo")
    upsert_repository(100, 200, "test-org", "repo-renamed", "test-org/repo-renamed")

    Session = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(bind=db, future=True)
    with Session() as session:
        rows = session.scalars(select(Repository)).all()
    assert len(rows) == 1
    assert rows[0].name == "repo-renamed"
