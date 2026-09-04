"use client";

import { useEffect, useState } from "react";

import { fetchArena, formatMoney, formatTimestamp } from "@/lib/arena";
import type { ArenaResponse, ArenaStatus } from "@/lib/types";
import { ModelPanel } from "./model-panel";


interface ArenaDashboardProps {
  initialData?: ArenaResponse;
  polling?: boolean;
  fetcher?: () => Promise<ArenaResponse>;
}


const statusLabels: Record<ArenaStatus, string> = {
  LIVE: "Live",
  REPLAY: "Historical replay",
  STALE: "Stale data",
  DEMO: "Demo data",
  WAITING: "Waiting for first run",
};


export function ArenaDashboard({
  initialData,
  polling = true,
  fetcher = fetchArena,
}: ArenaDashboardProps) {
  const [data, setData] = useState<ArenaResponse | undefined>(initialData);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const next = await fetcher();
        if (active) {
          setData(next);
          setError(null);
        }
      } catch {
        if (active) setError("Arena data is unavailable");
      }
    };

    if (!initialData) void refresh();
    const timer = polling ? window.setInterval(refresh, 15_000) : undefined;
    return () => {
      active = false;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [fetcher, initialData, polling]);

  if (!data && !error) {
    return <main className="state-screen">Preparing the arena…</main>;
  }
  if (!data) {
    return (
      <main className="state-screen error-state">
        <h1>Arena data is unavailable</h1>
        <p>Start the FastAPI service and run the seed command, then refresh this page.</p>
      </main>
    );
  }

  return (
    <main className="arena-shell">
      <header className="arena-header">
        <div className="arena-title">
          <span className="arena-mark" aria-hidden="true">$</span>
          <div>
            <h1>{formatMoney(data.startingCapital)}. Four open models. One market.</h1>
            <p>Equal capital, identical data, simulated execution.</p>
          </div>
        </div>
        <div className="arena-state">
          <span className={`status-dot status-${data.status.toLowerCase()}`} aria-hidden="true" />
          <div>
            <strong>{statusLabels[data.status]}</strong>
            <span>{formatTimestamp(data.asOf)}</span>
          </div>
        </div>
      </header>

      {error ? <p className="stale-banner">Refresh failed. Showing the last successful update.</p> : null}

      <section className="arena-grid" aria-label="Model performance arena">
        {data.models.map((model) => <ModelPanel key={model.id} model={model} />)}
      </section>

      <footer className="arena-footer">
        <span>Simulation only. No real orders are placed.</span>
        <span>Market data: Yahoo Finance · Benchmark: SPY</span>
      </footer>
    </main>
  );
}

