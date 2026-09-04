import { describe, expect, it } from "vitest";

import { formatMoney, formatPercent, projectTradeMarkers } from "./arena";
import type { EquitySeriesPoint, Trade } from "./types";


describe("arena formatting", () => {
  it("formats portfolio dollars without cents", () => {
    expect(formatMoney(103_492.2)).toBe("$103,492");
  });

  it("formats signed percentage returns", () => {
    expect(formatPercent(0.03492)).toBe("+3.49%");
    expect(formatPercent(-0.0117)).toBe("−1.17%");
    expect(formatPercent(0)).toBe("0.00%");
  });
});


describe("projectTradeMarkers", () => {
  it("places a trade on the nearest equity timestamp", () => {
    const series: EquitySeriesPoint[] = [
      {
        timestamp: "2026-09-01T14:00:00Z",
        equity: 100_000,
        returnPct: 0,
        benchmarkReturnPct: 0,
      },
      {
        timestamp: "2026-09-01T14:15:00Z",
        equity: 101_000,
        returnPct: 0.01,
        benchmarkReturnPct: 0.002,
      },
    ];
    const trades: Trade[] = [
      {
        id: 1,
        timestamp: "2026-09-01T14:13:00Z",
        side: "BUY",
        symbol: "NVDA",
        quantity: 10,
        price: 180,
        realizedPnl: 0,
      },
    ];

    expect(projectTradeMarkers(series, trades)).toEqual([
      {
        timestamp: "2026-09-01T14:15:00Z",
        returnPct: 0.01,
        side: "BUY",
        symbol: "NVDA",
        price: 180,
      },
    ]);
  });

  it("returns no markers without equity history", () => {
    expect(projectTradeMarkers([], [])).toEqual([]);
  });
});

