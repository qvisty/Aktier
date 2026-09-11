import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.db import Base
from backend import models  # noqa: F401


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def settings():
    return Settings(
        database_url="sqlite://",
        max_order_value_usd=100.0,
        max_positions=4,
        max_daily_orders=10,
        cash_buffer_pct=0.05,
        telegram_bot_token="",
        telegram_chat_id="",
        _env_file=None,
    )
