import type { ArenaResponse, EquitySeriesPoint, Trade, TradeMarker } from "./types";


const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");


export async function fetchArena(): Promise<ArenaResponse> {
  const response = await fetch(`${API_URL}/api/v1/arena?range=1w`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Arena API returned ${response.status}`);
  }
  return response.json() as Promise<ArenaResponse>;
}


export function formatMoney(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}


export function formatPercent(value: number): string {
  if (value === 0) return "0.00%";
  const magnitude = `${Math.abs(value * 100).toFixed(2)}%`;
  return value > 0 ? `+${magnitude}` : `−${magnitude}`;
}


export function projectTradeMarkers(
  series: EquitySeriesPoint[],
  trades: Trade[],
): TradeMarker[] {
  if (series.length === 0 || trades.length === 0) return [];
  return trades.map((trade) => {
    const tradeTime = Date.parse(trade.timestamp);
    const nearest = series.reduce((best, point) => {
      const bestDistance = Math.abs(Date.parse(best.timestamp) - tradeTime);
      const pointDistance = Math.abs(Date.parse(point.timestamp) - tradeTime);
      return pointDistance < bestDistance ? point : best;
    });
    return {
      timestamp: nearest.timestamp,
      returnPct: nearest.returnPct,
      side: trade.side,
      symbol: trade.symbol,
      price: trade.price,
    };
  });
}


export function formatTimestamp(timestamp: string | null): string {
  if (!timestamp) return "No completed cycle";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(timestamp));
}

