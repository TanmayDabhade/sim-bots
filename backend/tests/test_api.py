from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import _model_payload, create_app
from app.config import Settings
from app.database import Base
from app.db_models import ModelProfileRecord, TradeRecord
from app.models.provider import DemoModelProvider
from app.repositories import seed_models_and_portfolios
from app.schemas import MarketSnapshot, SymbolSnapshot


def snapshot() -> MarketSnapshot:
    now = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    return MarketSnapshot(
        as_of=now,
        status="DEMO",
        symbols=[
            SymbolSnapshot(
                symbol="NVDA",
                as_of=now,
                price=180.0,
                change_1d=0.02,
                change_1h=0.01,
                volume=1_000_000,
                sma_20=175.0,
                sma_50=170.0,
                rsi_14=55.0,
            ),
            SymbolSnapshot(
                symbol="SPY",
                as_of=now,
                price=600.0,
                change_1d=0.005,
                change_1h=0.001,
                volume=2_000_000,
                sma_20=598.0,
                sma_50=590.0,
                rsi_14=52.0,
            ),
        ],
    )


class FakeMarketProvider:
    async def get_snapshot(self, symbols: list[str], period: str, interval: str) -> MarketSnapshot:
        return snapshot()


def app_client(admin_token: str = "") -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        model_provider="demo",
        admin_token=admin_token,
        enable_scheduler=False,
    )
    app = create_app(
        settings=settings,
        session_factory=factory,
        market_provider=FakeMarketProvider(),
        model_provider=DemoModelProvider(),
    )
    return TestClient(app)


def test_health_and_readiness_report_demo_mode() -> None:
    with app_client() as client:
        assert client.get("/health").json() == {"status": "ok"}
        readiness = client.get("/ready")

    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"
    assert readiness.json()["modelProvider"] == "demo"


def test_arena_endpoint_returns_four_models_after_run() -> None:
    with app_client(admin_token="secret") as client:
        run = client.post("/api/v1/admin/arena/run-once", headers={"x-admin-token": "secret"})
        response = client.get("/api/v1/arena?range=1w")

    assert run.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DEMO"
    assert payload["startingCapital"] == 400_000.0
    assert [model["id"] for model in payload["models"]] == ["qwen", "gemma", "phi", "llama"]
    assert all(len(model["series"]) == 1 for model in payload["models"])
    assert all(len(model["recentTrades"]) == 1 for model in payload["models"])


def test_unknown_model_returns_not_found() -> None:
    with app_client() as client:
        response = client.get("/api/v1/models/unknown")

    assert response.status_code == 404
    assert response.json()["detail"] == "model not found"


def test_admin_run_is_hidden_without_configuration() -> None:
    with app_client() as client:
        response = client.post("/api/v1/admin/arena/run-once")

    assert response.status_code == 404


def test_admin_run_requires_matching_token() -> None:
    with app_client(admin_token="secret") as client:
        response = client.post("/api/v1/admin/arena/run-once")

    assert response.status_code == 401


def test_model_payload_counts_all_trades_but_returns_only_recent_twenty() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed_models_and_portfolios(session)
        model = session.scalar(
            select(ModelProfileRecord).where(ModelProfileRecord.slug == "qwen")
        )
        assert model is not None
        for index in range(25):
            session.add(
                TradeRecord(
                    order_id=index + 1,
                    model_id=model.id,
                    symbol="SPY",
                    side="BUY",
                    quantity=Decimal("1"),
                    fill_price=Decimal("600"),
                    realized_pnl=Decimal("0"),
                    executed_at=datetime(2026, 8, 1, tzinfo=UTC)
                    + timedelta(minutes=index),
                )
            )
        session.commit()

        payload = _model_payload(session, model, None)

    assert payload["tradeCount"] == 25
    assert len(payload["recentTrades"]) == 20
