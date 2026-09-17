from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_dirs() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.library_dir.mkdir(parents=True, exist_ok=True)


_ensure_dirs()

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import text

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Lightweight SQLite migrations for existing installs
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(provider_profiles)"))}
        if "is_full_url" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE provider_profiles ADD COLUMN is_full_url BOOLEAN NOT NULL DEFAULT 0"
                )
            )
        block_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(blocks)"))}
        if "font_size" not in block_cols:
            conn.execute(text("ALTER TABLE blocks ADD COLUMN font_size FLOAT NOT NULL DEFAULT 0"))
