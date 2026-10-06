import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts"

import {
  ChartCard,
  ChartFrame,
  ChartState,
} from "@/components/charts/ChartCard"
import {
  AXIS_COLOR,
  formatCountValue,
  formatPercentValue,
} from "@/components/charts/chart-config"
import {
  useAdminUsers,
  type AdminUser,
  type UserRole,
} from "@/features/admin/api"

/**
 * System users by role, derived from the administrator's own user list.
 *
 * The prototype showed a donut of role distribution with figures like
 * "Students at 40%". Those were illustration values, and nothing in the backend
 * returns them. This chart therefore counts the records the administrator
 * already has: `GET /accounts/users/` is the administrator's own verified
 * source for accounts, and counting those rows is arithmetic on real data
 * rather than a new aggregation.
 *
 * NFR-010 applies. The donut carries role totals only — never a name, email or
 * per-student breakdown — so it shows composition without exposing student-level
 * data to an aggregated view.
 *
 * Inactive accounts are excluded: the question is the composition of the people
 * who can actually use the system, and counting deactivated accounts would
 * overstate it. Their number is stated in the footer so nothing is hidden.
 */

interface RoleSlice {
  role: UserRole
  label: string
  value: number
  color: string
}

/** Matches the `--role-*` tokens the user badges already use. */
const ROLES: readonly {
  role: UserRole
  label: string
  color: string
}[] = [
  { role: "student", label: "Students", color: "var(--role-student)" },
  { role: "parent", label: "Parents", color: "var(--role-parent)" },
  { role: "faculty", label: "Faculty", color: "var(--role-faculty)" },
  { role: "guidance", label: "Guidance", color: "var(--role-guidance)" },
  { role: "admin", label: "Administrators", color: "var(--role-admin)" },
]

function toSlices(users: readonly AdminUser[]): {
  slices: RoleSlice[]
  activeCount: number
  inactiveCount: number
} {
  const active = users.filter((user) => user.is_active)

  const slices = ROLES.flatMap((entry) => {
    const value = active.filter((user) => user.role === entry.role).length
    // A role nobody holds would render a legend entry for an empty segment.
    if (value === 0) return []
    return [{ role: entry.role, label: entry.label, value, color: entry.color }]
  })

  return {
    slices,
    activeCount: active.length,
    inactiveCount: users.length - active.length,
  }
}

export function RoleDistributionChart() {
  const query = useAdminUsers()
  const users = query.data ?? []
  const { slices, activeCount, inactiveCount } = toSlices(users)

  const footer =
    activeCount > 0
      ? `${formatCountValue(activeCount)} active account${
          activeCount === 1 ? "" : "s"
        }.${
          inactiveCount > 0
            ? ` ${formatCountValue(inactiveCount)} deactivated account${
                inactiveCount === 1 ? "" : "s"
              } excluded.`
            : ""
        }`
      : undefined

  return (
    <ChartCard
      title="System users by role"
      description="Active accounts grouped by role. Counts only — no individual accounts are shown."
      footer={footer}
    >
      <ChartState
        isLoading={query.isLoading}
        error={query.isError ? query.error : null}
        loadingLabel="Loading user distribution"
        isEmpty={slices.length === 0}
        emptyMessage="There are no active user accounts to distribute."
      >
        <ChartFrame
          label={`Donut chart of active accounts by role: ${slices
            .map((slice) => `${slice.label} ${slice.value}`)
            .join(", ")}.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]!.payload as RoleSlice
                  const share =
                    activeCount > 0 ? (point.value / activeCount) * 100 : null
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{point.label}</p>
                      <p className="text-muted-foreground">
                        {formatCountValue(point.value)}{" "}
                        {point.value === 1 ? "account" : "accounts"}
                      </p>
                      {share !== null ? (
                        <p className="text-muted-foreground">
                          {formatPercentValue(share)} of active accounts
                        </p>
                      ) : null}
                    </div>
                  )
                }}
              />
              <Pie
                data={slices}
                dataKey="value"
                nameKey="label"
                innerRadius="55%"
                outerRadius="80%"
                paddingAngle={1}
                stroke="var(--background)"
                isAnimationActive={false}
              >
                {slices.map((slice) => (
                  <Cell key={slice.role} fill={slice.color} />
                ))}
              </Pie>
              <Legend
                verticalAlign="bottom"
                iconType="circle"
                formatter={(value) => (
                  <span style={{ color: AXIS_COLOR, fontSize: 12 }}>
                    {value}
                  </span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}
