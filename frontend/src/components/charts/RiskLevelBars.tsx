import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts"

import { ChartFrame } from "@/components/charts/ChartCard"
import { AXIS_COLOR, formatCountValue } from "@/components/charts/chart-config"
import { RISK_LEVEL_COLORS, riskLevelRows } from "@/lib/guidance-analytics"
import type { RiskAlert } from "@/features/guidance/api"

/**
 * Risk Level Distribution — horizontal bars, per the Dashboard reference.
 *
 * Derived from the alerts the page already holds: nothing here fetches. What
 * the chart owes the reader, and delivers:
 *
 * - maroon for high, a lighter red for moderate, pale pink for low — the
 *   colour follows the level's identity, not the order of the legend;
 * - the real count at the end of every bar, as text;
 * - equal bar heights and spacing so the lengths are the only variable;
 * - a compact frame that stays readable when the container narrows, with the
 *   axis reserved for the count so the labels do not truncate.
 */
export function RiskLevelBars({ alerts }: { alerts: readonly RiskAlert[] }) {
  const rows = riskLevelRows(alerts)
  if (rows.length === 0) return null

  return (
    <ChartFrame
      height={150}
      label={`Risk level distribution: ${rows
        .map((row) => `${row.label} ${row.count}`)
        .join(", ")}.`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 40, bottom: 4, left: 4 }}
        >
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis
            type="category"
            dataKey="label"
            tickLine={false}
            axisLine={false}
            // "Moderate Risk" is the longest label: anything narrower wraps it
            // onto two lines and the rows stop aligning.
            width={104}
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
          />
          <Bar
            dataKey="count"
            barSize={14}
            radius={[0, 3, 3, 0]}
            isAnimationActive={false}
          >
            {rows.map((row) => (
              <Cell
                key={row.level}
                fill={RISK_LEVEL_COLORS[row.level]}
                /* Low risk reads as a lighter tint: it is the least severe
                   level, and a full-strength bar would make it compete with
                   the ones above it. */
                fillOpacity={row.level === "low" ? 0.45 : 1}
              />
            ))}
            <LabelList
              dataKey="count"
              position="right"
              formatter={(value: unknown) => formatCountValue(Number(value))}
              className="fill-foreground text-xs font-semibold"
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}
