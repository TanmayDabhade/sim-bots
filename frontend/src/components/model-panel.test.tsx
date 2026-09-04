import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ArenaDashboard } from "./arena-dashboard";
import { ModelPanel } from "./model-panel";
import type { ArenaResponse, ModelArena } from "@/lib/types";


const model: ModelArena = {
  id: "qwen",
  name: "Qwen",
  color: "#2F6F8F",
  providerModelId: "qwen/qwen3-8b",
  portfolioValue: 103_492,
  returnPct: 0.03492,
  pnl: 3_492,
  cash: 34_120,
  tradeCount: 8,
  winRate: 0.5,
  sharpe: 1.2,
  maxDrawdown: -0.02,
  latestDecision: {
    action: "BUY",
    symbol: "NVDA",
    targetWeight: 0.15,
    confidence: 0.74,
    reason: "Relative momentum is strongest.",
    status: "approved",
    error: null,
    createdAt: "2026-09-01T14:15:00Z",
  },
  series: [
    {
      timestamp: "2026-09-01T14:15:00Z",
      equity: 103_492,
      returnPct: 0.03492,
      benchmarkReturnPct: 0.0091,
    },
  ],
  recentTrades: [
    {
      id: 1,
      timestamp: "2026-09-01T14:15:00Z",
      side: "BUY",
      symbol: "NVDA",
      quantity: 83.3,
      price: 180.05,
      realizedPnl: 0,
    },
  ],
};


const arena: ArenaResponse = {
  asOf: "2026-09-01T14:15:00Z",
  status: "DEMO",
  mode: "demo",
  startingCapital: 400_000,
  benchmark: {
    symbol: "SPY",
    series: [{ timestamp: "2026-09-01T14:15:00Z", returnPct: 0.0091 }],
  },
  models: [
    model,
    { ...model, id: "gemma", name: "Gemma" },
    { ...model, id: "phi", name: "Phi" },
    { ...model, id: "llama", name: "Llama" },
  ],
};


describe("ModelPanel", () => {
  it("shows portfolio return, trade, and latest decision", () => {
    render(<ModelPanel model={model} />);

    expect(screen.getByRole("heading", { name: "Qwen" })).toBeInTheDocument();
    expect(screen.getByText("$103,492")).toBeInTheDocument();
    expect(screen.getByText("+3.49%")).toBeInTheDocument();
    expect(screen.getByText("Buy NVDA")).toBeInTheDocument();
    expect(screen.getByText("Relative momentum is strongest.")).toBeInTheDocument();
  });
});


describe("ArenaDashboard", () => {
  it("renders all four model quadrants", () => {
    render(<ArenaDashboard initialData={arena} polling={false} />);

    for (const name of ["Qwen", "Gemma", "Phi", "Llama"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("Demo data")).toBeInTheDocument();
  });

  it("keeps clear error copy when the API is unavailable", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("offline"));
    render(<ArenaDashboard polling={false} fetcher={fetcher} />);

    await waitFor(() => {
      expect(screen.getByText("Arena data is unavailable")).toBeInTheDocument();
    });
  });
});

