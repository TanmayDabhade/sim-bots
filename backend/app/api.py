from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.arena.scheduler import start_scheduler
from app.arena.service import ArenaService, DuplicateArenaRunError, MarketProvider
from app.config import Settings, get_settings
from app.database import get_engine
from app.db_models import (
    ArenaRunRecord,
    DecisionRecord,
    EquitySnapshotRecord,
    ModelProfileRecord,
    PortfolioRecord,
    TradeRecord,
)
from app.market.provider import YahooFinanceProvider
from app.models.provider import DemoModelProvider, ModelProvider, OpenRouterModelProvider
from app.portfolio.metrics import calculate_metrics
from app.repositories import seed_models_and_portfolios
from app.schemas import EquityPoint, TradeSummary


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _window_start(window: str, latest: datetime | None) -> datetime | None:
    if latest is None or window == "all":
        return None
    durations = {"1d": timedelta(days=1), "1w": timedelta(days=7), "1m": timedelta(days=31)}
    if window not in durations:
        raise HTTPException(status_code=422, detail="range must be 1d, 1w, 1m, or all")
    return _aware(latest) - durations[window]


def _decision_payload(decision: DecisionRecord | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "action": decision.action,
        "symbol": decision.symbol,
        "targetWeight": decision.target_weight,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "status": decision.status,
        "error": decision.provider_error,
        "createdAt": decision.created_at,
    }


def _model_payload(
    session: Session,
    model: ModelProfileRecord,
    since: datetime | None,
) -> dict[str, Any]:
    portfolio = session.scalar(select(PortfolioRecord).where(PortfolioRecord.model_id == model.id))
    if portfolio is None:
        raise RuntimeError(f"portfolio missing for {model.slug}")

    equity_query = (
        select(EquitySnapshotRecord)
        .where(EquitySnapshotRecord.model_id == model.id)
        .order_by(EquitySnapshotRecord.captured_at.asc())
    )
    if since is not None:
        equity_query = equity_query.where(EquitySnapshotRecord.captured_at >= since)
    snapshots = session.scalars(equity_query).all()
    trades = session.scalars(
        select(TradeRecord)
        .where(TradeRecord.model_id == model.id)
        .order_by(TradeRecord.executed_at.desc())
    ).all()
    recent_trades = list(reversed(trades[:20]))
    latest_decision = session.scalar(
        select(DecisionRecord)
        .where(DecisionRecord.model_id == model.id)
        .order_by(DecisionRecord.created_at.desc(), DecisionRecord.id.desc())
        .limit(1)
    )

    metric_points: list[EquityPoint] = []
    if snapshots:
        metric_points.append(
            EquityPoint(
                timestamp=_aware(snapshots[0].captured_at) - timedelta(microseconds=1),
                equity=float(portfolio.starting_cash),
            )
        )
        metric_points.extend(
            EquityPoint(timestamp=_aware(item.captured_at), equity=float(item.total_value))
            for item in snapshots
        )
    metrics = calculate_metrics(
        metric_points,
        [TradeSummary(realized_pnl=float(trade.realized_pnl)) for trade in trades],
    )
    latest_value = float(snapshots[-1].total_value) if snapshots else float(portfolio.cash)
    latest_return = (
        snapshots[-1].return_pct
        if snapshots
        else (latest_value / float(portfolio.starting_cash)) - 1.0
    )

    return {
        "id": model.slug,
        "name": model.name,
        "color": model.color,
        "providerModelId": model.provider_model_id,
        "portfolioValue": latest_value,
        "returnPct": latest_return,
        "pnl": latest_value - float(portfolio.starting_cash),
        "cash": float(portfolio.cash),
        "tradeCount": len(trades),
        "winRate": metrics.win_rate,
        "sharpe": metrics.sharpe,
        "maxDrawdown": metrics.max_drawdown,
        "latestDecision": _decision_payload(latest_decision),
        "series": [
            {
                "timestamp": item.captured_at,
                "equity": float(item.total_value),
                "returnPct": item.return_pct,
                "benchmarkReturnPct": item.benchmark_return_pct,
            }
            for item in snapshots
        ],
        "recentTrades": [
            {
                "id": trade.id,
                "timestamp": trade.executed_at,
                "side": trade.side,
                "symbol": trade.symbol,
                "quantity": float(trade.quantity),
                "price": float(trade.fill_price),
                "realizedPnl": float(trade.realized_pnl),
            }
            for trade in recent_trades
        ],
    }


def _arena_payload(session: Session, window: str) -> dict[str, Any]:
    latest_run = session.scalar(
        select(ArenaRunRecord).order_by(ArenaRunRecord.run_at.desc()).limit(1)
    )
    since = _window_start(window, latest_run.run_at if latest_run else None)
    models = session.scalars(select(ModelProfileRecord).order_by(ModelProfileRecord.id.asc())).all()
    model_payloads = [_model_payload(session, model, since) for model in models]
    benchmark = model_payloads[0]["series"] if model_payloads else []
    return {
        "asOf": latest_run.run_at if latest_run else None,
        "status": latest_run.market_status if latest_run else "WAITING",
        "mode": latest_run.mode if latest_run else None,
        "startingCapital": sum(float(model.portfolio.starting_cash) for model in models),
        "benchmark": {
            "symbol": "SPY",
            "series": [
                {
                    "timestamp": point["timestamp"],
                    "returnPct": point["benchmarkReturnPct"],
                }
                for point in benchmark
            ],
        },
        "models": model_payloads,
    }


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    market_provider: MarketProvider | None = None,
    model_provider: ModelProvider | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    factory = session_factory or sessionmaker(bind=get_engine(), expire_on_commit=False)
    market = market_provider or YahooFinanceProvider()
    models = model_provider or (
        OpenRouterModelProvider(
            active_settings.openrouter_api_key,
            active_settings.openrouter_base_url,
        )
        if active_settings.model_provider == "openrouter"
        else DemoModelProvider()
    )
    service = ArenaService(factory, market, models, active_settings)
    scheduler: Any | None = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal scheduler
        with factory() as session:
            seed_models_and_portfolios(session, active_settings)
        if active_settings.enable_scheduler:
            scheduler = start_scheduler(service, active_settings.arena_interval_minutes)
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="AI Market Arena API", version="0.1.0", lifespan=lifespan)
    app.state.arena_service = service
    app.state.market_provider = market
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type", "x-admin-token"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        with factory() as session:
            session.execute(text("SELECT 1"))
        if (
            active_settings.model_provider == "openrouter"
            and not active_settings.openrouter_api_key
        ):
            raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is missing")
        return {
            "status": "ready",
            "database": "connected",
            "modelProvider": active_settings.model_provider,
            "marketProvider": "yfinance",
        }

    @app.get("/api/v1/arena")
    def arena(window: str = Query(default="1w", alias="range")) -> dict[str, Any]:
        with factory() as session:
            return _arena_payload(session, window)

    @app.get("/api/v1/market/snapshot")
    async def market_snapshot() -> dict[str, Any]:
        current = await market.get_snapshot(
            sorted(ALLOWED_API_SYMBOLS),
            active_settings.market_period,
            active_settings.market_interval,
        )
        return current.model_dump(mode="json")

    @app.get("/api/v1/models/{slug}")
    def model(slug: str, window: str = Query(default="1w", alias="range")) -> dict[str, Any]:
        with factory() as session:
            payload = _arena_payload(session, window)
        found = next((item for item in payload["models"] if item["id"] == slug), None)
        if found is None:
            raise HTTPException(status_code=404, detail="model not found")
        return cast(dict[str, Any], found)

    @app.get("/api/v1/models/{slug}/trades")
    def model_trades(slug: str) -> list[dict[str, Any]]:
        with factory() as session:
            payload = _arena_payload(session, "all")
        found = next((item for item in payload["models"] if item["id"] == slug), None)
        if found is None:
            raise HTTPException(status_code=404, detail="model not found")
        return cast(list[dict[str, Any]], found["recentTrades"])

    @app.post("/api/v1/admin/arena/run-once")
    async def run_once(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        if not active_settings.admin_token:
            raise HTTPException(status_code=404, detail="not found")
        if x_admin_token != active_settings.admin_token:
            raise HTTPException(status_code=401, detail="invalid admin token")
        now = datetime.now(UTC).replace(microsecond=0)
        try:
            result = await service.run_once(now, mode=active_settings.model_provider)
        except DuplicateArenaRunError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    return app


ALLOWED_API_SYMBOLS = {"SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META", "TSLA", "JPM"}
