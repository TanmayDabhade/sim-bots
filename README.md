# AI Market Arena

**$400,000. Four open models. One market.**

AI Market Arena gives Qwen, Gemma, Phi, and Llama identical price/technical
data and a separate $100,000 simulated portfolio. Every decision passes through
the same risk rules and simulated broker. The single-page Next.js dashboard
shows each model in its own quadrant with returns, an SPY benchmark, trade
markers, portfolio statistics, and recent reasoning.

The default setup is credential-free: Yahoo Finance supplies delayed market
data and deterministic demo strategies make the four decisions. Set one API
key to replace those demo strategies with hosted OpenRouter inference. Nothing
runs on your laptop's GPU and the application never places real orders.

## Included

- Next.js 16, TypeScript, Tailwind CSS, and Recharts frontend
- FastAPI, SQLAlchemy, Alembic, and PostgreSQL backend
- Batched one-minute Yahoo Finance data for SPY, QQQ, AAPL, MSFT, NVDA,
  AMZN, GOOG, META, TSLA, and JPM
- SMA-20, SMA-50, RSI-14, one-hour change, and one-day change
- Four independently configured OpenRouter models with strict local response
  validation, one repair attempt, and safe HOLD fallback
- No leverage, no shorting, 20% maximum position weight, a configurable daily
  trade limit (390 per model by default), and a 2% minimum allocation change
- Three-basis-point adverse simulated slippage, order/trade audit history,
  SPY benchmark, return, P&L, Sharpe, max drawdown, and win rate
- Historical replay seeding and an NYSE-calendar-aware live scheduler
- Docker Compose and local-development workflows

## Fastest start: Docker

Requirements: Docker Desktop with Compose.

1. Copy `.env.example` to `.env`. The repository already includes safe demo
   defaults, so no credential is required.
2. Start the full stack:

   ```bash
   docker compose up --build -d
   ```

   The backend automatically applies migrations and creates the four starting
   portfolios.
3. Seed eight historical arena cycles from Yahoo Finance:

   ```bash
   docker compose exec backend python -m app.cli seed --steps 8
   ```

4. Open `http://localhost:3000`. The API is available at
   `http://localhost:8000` and its interactive documentation at
   `http://localhost:8000/docs`.

Stop the stack with `docker compose down`. PostgreSQL data stays in the named
Docker volume; add `--volumes` only when you intentionally want to erase it.

## Hosted model mode

Create an OpenRouter key, then change these values in `.env`:

```dotenv
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key-here
ENABLE_SCHEDULER=true
ARENA_INTERVAL_MINUTES=1
MARKET_INTERVAL=1m
MARKET_PERIOD=5d
MAX_DAILY_TRADES=390
ADMIN_TOKEN=choose-a-long-random-token
```

The default model IDs are:

```text
qwen/qwen3-8b
google/gemma-3-12b-it
microsoft/phi-4
meta-llama/llama-3.1-8b-instruct
```

They remain environment variables so a retired or unavailable endpoint can be
replaced without a code change. Restart the backend after editing `.env`:

```bash
docker compose up --build -d backend frontend
```

With the scheduler enabled, the service attempts its first cycle immediately
at startup and evaluates every minute during regular NYSE sessions, respecting
holidays and early closes. The four models evaluate concurrently; slow cycles
do not overlap. A model may choose HOLD on any cycle. Prices are Yahoo bars,
which may be delayed, not an exchange tick stream. Positions can remain open
overnight; there is no mandatory closing-bell liquidation.

The dashboard and `/api/v1/arena` expose whether the scheduler is disabled,
the market is closed, a cycle is running, a cycle failed, or demo rules are active.
`/ready` also reports the configured provider and scheduler interval.

For Render, set these environment variables on the **backend** and redeploy.
Existing environment values override the new defaults. Use an always-running
service and a persistent database. Render Free services sleep after 15 minutes
without inbound traffic, stopping the in-process scheduler, and local SQLite
changes are lost on restart. Run exactly **one backend process/replica** with
the scheduler enabled; its overlap protection is within that process.
See https://render.com/docs/free for hosting limitations.

At one cycle per minute, four hosted models can make approximately 1,560 primary
requests in a full 390-minute session, plus any JSON repair requests.
Historical replay seeding is optional and is not required for live cycles.

To trigger a protected cycle manually:

```bash
curl -X POST http://localhost:8000/api/v1/admin/arena/run-once \
  -H "x-admin-token: choose-a-long-random-token"
```

OpenRouter usage can incur charges. If a hosted request times out, fails, or
returns malformed data twice, that model records a HOLD and the other models
continue.

## Local development

Requirements: Python 3.12+, Node.js 24+, npm, and Docker for PostgreSQL.

```bash
make install
make db-up
make init-db
make seed
```

Run these in separate terminals:

```bash
make dev-backend
make dev-frontend
```

Useful commands:

```bash
make test          # backend and frontend tests
make check         # tests, lint, types, and production frontend build
make arena-once    # one current market cycle
make migrate       # apply Alembic migrations
```

## API

```text
GET  /health
GET  /ready
GET  /api/v1/arena?range=1w
GET  /api/v1/market/snapshot
GET  /api/v1/models/{qwen|gemma|phi|llama}
GET  /api/v1/models/{qwen|gemma|phi|llama}/trades
POST /api/v1/admin/arena/run-once
```

Arena ranges are `1d`, `1w`, `1m`, or `all`. The admin endpoint is hidden
unless `ADMIN_TOKEN` is configured.

## Architecture

```text
Yahoo Finance -> normalized market snapshot -> four decision providers
     -> shared risk engine -> simulated broker -> PostgreSQL
     -> FastAPI JSON API -> four-quadrant Next.js dashboard
```

`MODEL_PROVIDER=demo` is an explicit no-credential simulation mode. It uses four
small deterministic rules so that setup, replay, trades, and charts are useful
before connecting paid inference. `MODEL_PROVIDER=openrouter` sends the exact
same prompt and portfolio schema to each hosted model.

## Important limitations

- This is a simulation and research project, not financial advice.
- No real brokerage integration or order placement exists.
- Yahoo Finance data can be delayed, revised, unavailable, or unsuitable for
  commercial use. Check Yahoo's terms before deploying publicly.
- Replay decisions are a seeded demonstration, not a claim of historical model
  performance or a bias-free backtest.
- Credentials belong only in `.env`; that file is ignored by source control.
# sim-bots
