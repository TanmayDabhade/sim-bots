from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db_models import ModelProfileRecord, PortfolioRecord

MODEL_PROFILES = (
    ("qwen", "Qwen", "#2F6F8F"),
    ("gemma", "Gemma", "#B77A21"),
    ("phi", "Phi", "#19745B"),
    ("llama", "Llama", "#C74D3C"),
)


def seed_models_and_portfolios(session: Session, settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    for slug, name, color in MODEL_PROFILES:
        model = session.scalar(select(ModelProfileRecord).where(ModelProfileRecord.slug == slug))
        if model is None:
            model = ModelProfileRecord(
                slug=slug,
                name=name,
                color=color,
                provider_model_id=active_settings.model_ids[slug],
            )
            session.add(model)
            session.flush()
        else:
            model.name = name
            model.color = color
            model.provider_model_id = active_settings.model_ids[slug]

        portfolio = session.scalar(
            select(PortfolioRecord).where(PortfolioRecord.model_id == model.id)
        )
        if portfolio is None:
            session.add(
                PortfolioRecord(
                    model_id=model.id,
                    cash=Decimal("100000"),
                    starting_cash=Decimal("100000"),
                )
            )
    session.commit()
