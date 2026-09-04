from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.db_models import ModelProfileRecord, PortfolioRecord
from app.repositories import seed_models_and_portfolios


def test_seed_creates_four_unique_funded_portfolios_idempotently() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_models_and_portfolios(session)
        seed_models_and_portfolios(session)

        model_count = session.scalar(select(func.count()).select_from(ModelProfileRecord))
        portfolio_count = session.scalar(select(func.count()).select_from(PortfolioRecord))
        balances = session.scalars(select(PortfolioRecord.cash)).all()
        slugs = session.scalars(
            select(ModelProfileRecord.slug).order_by(ModelProfileRecord.slug)
        ).all()

    assert model_count == 4
    assert portfolio_count == 4
    assert balances == [100_000.0, 100_000.0, 100_000.0, 100_000.0]
    assert slugs == ["gemma", "llama", "phi", "qwen"]
