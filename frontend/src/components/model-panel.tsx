"use client";

import type { CSSProperties } from "react";

import { formatMoney, formatPercent } from "@/lib/arena";
import type { ModelArena } from "@/lib/types";
import { ReturnChart } from "./return-chart";


interface ModelPanelProps {
  model: ModelArena;
}


function actionLabel(model: ModelArena): string {
  const decision = model.latestDecision;
  if (!decision || decision.action === "HOLD") return "Hold";
  const verb = decision.action === "BUY" ? "Buy" : "Sell";
  return `${verb} ${decision.symbol}`;
}


export function ModelPanel({ model }: ModelPanelProps) {
  const returnTone = model.returnPct > 0 ? "positive" : model.returnPct < 0 ? "negative" : "neutral";
  const panelStyle = { "--model-accent": model.color } as CSSProperties;

  return (
    <article className="model-panel" style={panelStyle}>
      <header className="model-header">
        <div>
          <h2>{model.name}</h2>
          <p className="model-id">{model.providerModelId}</p>
        </div>
        <div className="model-value">
          <strong>{formatMoney(model.portfolioValue)}</strong>
          <span className={returnTone}>{formatPercent(model.returnPct)}</span>
        </div>
      </header>

      <div className="chart-legend" aria-hidden="true">
        <span><i className="legend-model" />{model.name}</span>
        <span><i className="legend-spy" />SPY</span>
        <span><i className="legend-buy" />Buy</span>
        <span><i className="legend-sell" />Sell</span>
      </div>

      <ReturnChart
        name={model.name}
        color={model.color}
        series={model.series}
        trades={model.recentTrades}
      />

      <dl className="model-stats">
        <div><dt>Cash</dt><dd>{formatMoney(model.cash)}</dd></div>
        <div><dt>Trades</dt><dd>{model.tradeCount}</dd></div>
        <div><dt>Drawdown</dt><dd>{formatPercent(model.maxDrawdown)}</dd></div>
        <div><dt>Win rate</dt><dd>{model.winRate === null ? "—" : formatPercent(model.winRate)}</dd></div>
      </dl>

      <section className="decision" aria-label={`${model.name} latest decision`}>
        <div className="decision-line">
          <strong>{actionLabel(model)}</strong>
          {model.latestDecision ? (
            <span>{formatPercent(model.latestDecision.confidence)} confidence</span>
          ) : null}
        </div>
        <p>
          {model.latestDecision?.reason ?? "Waiting for this model's first decision."}
        </p>
        {model.latestDecision?.error ? (
          <p className="decision-error">{model.latestDecision.error}</p>
        ) : null}
      </section>

      {model.recentTrades.length > 0 ? (
        <ul className="recent-trades" aria-label={`${model.name} recent trades`}>
          {model.recentTrades.slice(-3).reverse().map((trade) => (
            <li key={trade.id}>
              <span className={trade.side === "BUY" ? "trade-buy" : "trade-sell"}>
                {trade.side === "BUY" ? "Bought" : "Sold"} {trade.symbol}
              </span>
              <span>{trade.quantity.toFixed(2)} @ {formatMoney(trade.price)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

