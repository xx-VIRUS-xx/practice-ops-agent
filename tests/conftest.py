import datetime
import os
import uuid

import pytest
from cryptography.fernet import Fernet

# Ensure a valid encryption key + isolated sqlite DB are set BEFORE any
# app module is imported (Settings is read at import time in some modules).
os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.orm import Practice


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def practice(db_session):
    p = Practice(id=str(uuid.uuid4()), name="Test Practice")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def dt(hour: int, minute: int = 0, day: int = 15) -> datetime.datetime:
    return datetime.datetime(2026, 9, day, hour, minute, tzinfo=datetime.timezone.utc)
