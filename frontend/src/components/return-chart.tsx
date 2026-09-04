"use client";

import { Cell, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";

import { formatPercent, projectTradeMarkers } from "@/lib/arena";
import type { EquitySeriesPoint, Trade } from "@/lib/types";


interface ReturnChartProps {
  name: string;
  color: string;
  series: EquitySeriesPoint[];
  trades: Trade[];
}


export function ReturnChart({ name, color, series, trades }: ReturnChartProps) {
  if (series.length === 0) {
    return <div className="chart-empty">The first equity point will appear after an arena cycle.</div>;
  }
  const markers = projectTradeMarkers(series, trades);

  return (
    <div className="chart" role="img" aria-label={`${name} return compared with SPY`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} syncId="arena" margin={{ top: 12, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#B9C5CB" strokeDasharray="2 6" vertical={false} />
          <XAxis dataKey="timestamp" hide />
          <YAxis
            width={50}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#526874", fontSize: 11 }}
            tickFormatter={(value: number) => formatPercent(value)}
            domain={["auto", "auto"]}
          />
          <Tooltip
            cursor={{ stroke: "#71818A", strokeDasharray: "3 3" }}
            formatter={(value, label) => [
              formatPercent(Number(value)),
              label === "returnPct" ? name : "SPY",
            ]}
            labelFormatter={(value) => new Date(String(value)).toLocaleString()}
            contentStyle={{
              background: "#F6F8F9",
              border: "1px solid #71818A",
              borderRadius: 0,
              color: "#102A3A",
              fontSize: 12,
            }}
          />
          <ReferenceLine y={0} stroke="#71818A" strokeOpacity={0.6} />
          <Line
            type="monotone"
            dataKey="benchmarkReturnPct"
            name="SPY"
            stroke="#71818A"
            strokeWidth={1.5}
            strokeDasharray="5 5"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="returnPct"
            name={name}
            stroke={color}
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
            isAnimationActive={false}
          />
          <Scatter data={markers} dataKey="returnPct" isAnimationActive={false}>
            {markers.map((marker, index) => (
              <Cell
                key={`${marker.timestamp}-${marker.symbol}-${index}`}
                fill={marker.side === "BUY" ? "#19745B" : "#C74D3C"}
                stroke="#F6F8F9"
                strokeWidth={1.5}
              />
            ))}
          </Scatter>
        </ComposedChart>
      </ResponsiveContainer>
      <span className="sr-only">
        {series.length} equity points and {markers.length} trades.
      </span>
    </div>
  );
}

