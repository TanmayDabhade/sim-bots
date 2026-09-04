export type ArenaStatus = "LIVE" | "REPLAY" | "STALE" | "DEMO" | "WAITING";
export type TradeSide = "BUY" | "SELL";
export type DecisionAction = TradeSide | "HOLD";

export interface EquitySeriesPoint {
  timestamp: string;
  equity: number;
  returnPct: number;
  benchmarkReturnPct: number;
}

export interface Trade {
  id: number;
  timestamp: string;
  side: TradeSide;
  symbol: string;
  quantity: number;
  price: number;
  realizedPnl: number;
}

export interface LatestDecision {
  action: DecisionAction;
  symbol: string | null;
  targetWeight: number | null;
  confidence: number;
  reason: string;
  status: string;
  error: string | null;
  createdAt: string;
}

export interface ModelArena {
  id: string;
  name: string;
  color: string;
  providerModelId: string;
  portfolioValue: number;
  returnPct: number;
  pnl: number;
  cash: number;
  tradeCount: number;
  winRate: number | null;
  sharpe: number | null;
  maxDrawdown: number;
  latestDecision: LatestDecision | null;
  series: EquitySeriesPoint[];
  recentTrades: Trade[];
}

export interface ArenaResponse {
  asOf: string | null;
  status: ArenaStatus;
  mode: string | null;
  startingCapital: number;
  benchmark: {
    symbol: "SPY";
    series: Array<{ timestamp: string; returnPct: number }>;
  };
  models: ModelArena[];
}

export interface TradeMarker {
  timestamp: string;
  returnPct: number;
  side: TradeSide;
  symbol: string;
  price: number;
}

