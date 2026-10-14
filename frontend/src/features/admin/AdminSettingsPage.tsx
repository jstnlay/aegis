import { Settings } from "lucide-react"
import { useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { normalizeApiError } from "@/lib/error"
import {
  useSystemSettings,
  useUpdateSystemSetting,
  type SystemSetting,
} from "@/features/admin/api"

/**
 * FR-034 / TC-ADM-11: the administrator's system-wide settings page.
 *
 * The QA row asks for settings that are "successfully updated and applied
 * across the system", which is two separate claims. Updating is the form below.
 * Applied is the harder half and it is paid for in the backend - the attendance
 * threshold is read at the moment of the write, not cached at startup - so this
 * page can promise an immediate effect without a save-time reload and mean it.
 *
 * Each row states what it affects and where, because "applies across the
 * system" means nothing to someone deciding whether to raise a threshold.
 */
export function AdminSettingsPage() {
  const settingsQuery = useSystemSettings()
  const settings = settingsQuery.data ?? []

  if (settingsQuery.isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <div className="space-y-3">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-28 w-full" />
          ))}
        </div>
      </div>
    )
  }

  if (settingsQuery.isError) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <ErrorNote message={normalizeApiError(settingsQuery.error).message} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader />

      {settings.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No settings are registered. Settings are seeded from the backend
            registry, so this page reflects what the code actually reads rather
            than a table maintained by hand.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {settings.map((setting) => (
            <SettingRow key={setting.key} setting={setting} />
          ))}
        </div>
      )}
    </div>
  )
}

function PageHeader() {
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-2xl font-bold text-foreground">
        System-wide Settings
      </h2>
      <Badge
        variant="outline"
        className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
      >
        <Settings className="mr-1.5 size-3.5" aria-hidden="true" />
        Applied immediately
      </Badge>
      <p className="text-sm text-muted-foreground">
        Changes take effect on the next action they govern. No restart, no
        reload.
      </p>
    </div>
  )
}

/**
 * One editable setting.
 *
 * The draft lives here rather than in the parent so a row is only dirty when
 * that row is edited - saving one setting must not submit the others.
 */
function SettingRow({ setting }: { setting: SystemSetting }) {
  const [draft, setDraft] = useState<string | null>(null)
  const [savedValue, setSavedValue] = useState<string | null>(null)
  const update = useUpdateSystemSetting()

  const current = savedValue ?? setting.value
  const pending = draft ?? current
  const isDirty = pending !== current

  const expectsInteger = setting.value_type === "int"
  const invalid =
    expectsInteger && (pending.trim() === "" || !/^-?\d+$/.test(pending.trim()))

  const resolvedValue = isDirty ? pending : current
  const savedAt = useMemo(
    () =>
      setting.updated_at ? new Date(setting.updated_at).toLocaleString() : null,
    [setting.updated_at]
  )

  function handleSave() {
    if (invalid) return
    update.mutate(
      { key: setting.key, value: pending.trim() },
      {
        onSuccess: () => {
          setSavedValue(pending.trim())
          setDraft(null)
        },
      }
    )
  }

  function handleReset() {
    setDraft(null)
    update.reset()
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="text-base">
              {setting.description ?? setting.key}
            </CardTitle>
            <CardDescription className="mt-1 font-mono text-xs">
              {setting.key}
            </CardDescription>
          </div>
          {savedAt ? (
            <span className="text-xs text-muted-foreground">
              {setting.updated_by_email ? (
                <>
                  Saved by {setting.updated_by_email} · {savedAt}
                </>
              ) : (
                <>Defaults applied · {savedAt}</>
              )}
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="space-y-1.5">
            <Label htmlFor={`setting-${setting.key}`}>Value</Label>
            <Input
              id={`setting-${setting.key}`}
              value={resolvedValue}
              inputMode={expectsInteger ? "numeric" : undefined}
              aria-invalid={invalid || undefined}
              aria-describedby={`setting-${setting.key}-hint`}
              onChange={(event) => setDraft(event.target.value)}
              className="w-40"
            />
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!isDirty || invalid || update.isPending}
              onClick={handleSave}
            >
              {update.isPending ? "Saving…" : "Save"}
            </Button>
            {isDirty ? (
              <Button
                size="sm"
                variant="outline"
                onClick={handleReset}
                disabled={update.isPending}
              >
                Discard
              </Button>
            ) : null}
          </div>
        </div>

        <p
          id={`setting-${setting.key}-hint`}
          className="text-xs text-muted-foreground"
        >
          {invalid ? (
            <span className="text-destructive">
              This setting holds a whole number.
            </span>
          ) : (
            <>
              Default {String(setting.default)}
              {/* Stating where a setting bites is what makes "applied across
                  the system" checkable rather than a slogan. */}
              {AFFECTS[setting.key] ? ` · ${AFFECTS[setting.key]}` : null}
            </>
          )}
        </p>

        {update.isError ? (
          <ErrorNote message={normalizeApiError(update.error).message} />
        ) : null}
      </CardContent>
    </Card>
  )
}

/**
 * What each setting governs, stated for the person reading the page.
 *
 * Kept in the frontend because it is user-facing prose, not behaviour - the
 * backend's `description` is the control's label, this is where the label's
 * effect lands. The two are not duplicated: this never says what a setting
 * means, only where it is felt.
 */
const AFFECTS: Record<string, string> = {
  "attendance.absence_threshold":
    "Read when an absence is recorded; parents are alerted on reaching it.",
  "assessment.default_time_limit":
    "Pre-fills the time limit on a new assessment.",
  "guidance.risk_score_threshold":
    "Determines which students count as at-risk on the guidance dashboard.",
}
