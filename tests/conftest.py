import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import Settings
from app.db import Base, get_db
from app.main import app, get_keitaro
from fake_keitaro import FakeKeitaro


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def kt():
    return FakeKeitaro()


@pytest.fixture
def settings():
    return Settings(keitaro_api_key="test")


@pytest.fixture
def client(db, kt):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_keitaro] = lambda: kt
    yield TestClient(app)
    app.dependency_overrides.clear()
