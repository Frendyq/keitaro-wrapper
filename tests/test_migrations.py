from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.db import Base

ROOT = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def test_migration_matches_the_models(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        config = alembic_config()
        command.upgrade(config, "head")

        engine = create_engine(url)
        with engine.connect() as connection:
            # No differences means the migration builds exactly the schema of the models.
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert {"campaigns", "streams", "stream_offers"} <= set(inspect(engine).get_table_names())

        command.downgrade(config, "base")
        assert "campaigns" not in inspect(create_engine(url)).get_table_names()
    finally:
        get_settings.cache_clear()
