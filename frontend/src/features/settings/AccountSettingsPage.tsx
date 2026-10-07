import { Settings } from "lucide-react"
import { useState, type FormEvent } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useChangePassword,
  useCurrentUser,
  useNotificationPreference,
  useUpdateNotificationPreference,
  useUpdateProfile,
  optionalText,
  type CurrentUser,
  type NotificationPreference,
} from "@/features/settings/api"
import { normalizeApiError } from "@/lib/error"

/**
 * `PasswordChangeSerializer.validate_new_password` enforces `min_length=8`
 * before the project's own `validate_password` runs, so 8 is the floor the form
 * can check without guessing at the rest of the policy.
 */
const MIN_PASSWORD_LENGTH = 8

/**
 * Trims a `TimeField` value to the `HH:MM` an `<input type="time">` accepts.
 *
 * DRF serializes `TimeField` as `HH:MM:SS`, but a time input rejects the
 * seconds segment and reports itself as empty, which would make a stored
 * preference look as though it had been lost.
 */
function toTimeInputValue(value: string | null): string {
  return value ? value.slice(0, 5) : ""
}

function PageHeading() {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <Settings className="size-5 text-muted-foreground" aria-hidden="true" />
        <h2 className="text-2xl font-bold text-foreground">Account settings</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Your own profile and password. Role, status, and sign-in identity are
        managed by an administrator and cannot be changed here.
      </p>
    </div>
  )
}

function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <span>{message}</span>
    </div>
  )
}

function SuccessNote({ message }: { message: string }) {
  return (
    <p
      role="status"
      className="rounded-md border border-success/30 bg-success/10 p-3 text-sm text-success"
    >
      {message}
    </p>
  )
}

/**
 * Profile form.
 *
 * Seeds from `useCurrentUser`. The seed runs once per loaded user identity
 * rather than on every render, so an in-progress edit is not clobbered by a
 * background refetch of the same account.
 */
/**
 * The seeded profile form.
 *
 * Split out from `ProfileSection` and keyed on the user id: the local draft is
 * initialized from the `user` prop in `useState`, and a new id remounts the
 * component with fresh initial values. That avoids the cascading render of a
 * setState-in-effect seed, and it also means a background refetch of the same
 * account cannot clobber an edit in progress.
 */
function ProfileForm({ user }: { user: CurrentUser }) {
  const update = useUpdateProfile()

  const [firstName, setFirstName] = useState(user.first_name)
  const [lastName, setLastName] = useState(user.last_name)
  const [phoneNumber, setPhoneNumber] = useState(user.phone_number ?? "")
  const [address, setAddress] = useState(user.address ?? "")
  const [language, setLanguage] = useState(user.language_preference ?? "")

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      await update.mutateAsync({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: optionalText(phoneNumber),
        address: optionalText(address),
        language_preference: optionalText(language),
      })
    } catch {
      // Surfaced from `update.isError` below; the form keeps the typed values.
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle>Profile</CardTitle>
          <CardDescription>
            Names and contact details, as the signed-in account.
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="profile-first-name">First name</Label>
              <Input
                id="profile-first-name"
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="profile-last-name">Last name</Label>
              <Input
                id="profile-last-name"
                value={lastName}
                onChange={(event) => setLastName(event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="profile-phone">Phone number</Label>
            <Input
              id="profile-phone"
              type="tel"
              value={phoneNumber}
              onChange={(event) => setPhoneNumber(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Optional. Clearing this sends null.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="profile-address">Address</Label>
            <Input
              id="profile-address"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">Optional.</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="profile-language">Language preference</Label>
            <Input
              id="profile-language"
              value={language}
              maxLength={10}
              onChange={(event) => setLanguage(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Optional, up to 10 characters. The server stores this as free
              text.
            </p>
          </div>

          {update.isError ? (
            <ErrorNote message={normalizeApiError(update.error).message} />
          ) : null}
          {update.isSuccess ? <SuccessNote message="Profile saved." /> : null}

          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save profile"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

/**
 * Loads the account and mounts the keyed `ProfileForm`.
 *
 * The form is not rendered at all until the user has loaded, so its state
 * initializer always has real values to read.
 */
function ProfileSection() {
  const userQuery = useCurrentUser()

  if (userQuery.isLoading) return <Skeleton className="h-64 w-full" />
  if (userQuery.isError) {
    return (
      <Card>
        <CardContent className="pt-6">
          <ErrorNote message={normalizeApiError(userQuery.error).message} />
        </CardContent>
      </Card>
    )
  }

  const user = userQuery.data
  if (!user) return null

  return <ProfileForm key={user.id} user={user} />
}

/** Read-only identity summary. Nothing here is writable through `/accounts/me/`. */
function IdentityCard() {
  const userQuery = useCurrentUser()

  if (userQuery.isLoading) return <Skeleton className="h-32 w-full" />
  if (userQuery.isError) {
    return (
      <Card>
        <CardContent className="pt-6">
          <ErrorNote message={normalizeApiError(userQuery.error).message} />
        </CardContent>
      </Card>
    )
  }

  const user = userQuery.data
  if (!user) return null

  return (
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle>Account</CardTitle>
          <CardDescription>
            Managed by an administrator. These fields are read-only.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">Email</div>
            <div className="text-sm" data-account-field="email">
              {user.email}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">Username</div>
            <div className="text-sm" data-account-field="username">
              {user.username}
            </div>
          </div>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Role</div>
          <Badge
            variant="outline"
            data-account-field="role"
            className="capitalize"
          >
            {user.role}
          </Badge>
        </div>
      </CardContent>
    </Card>
  )
}

/** `POST /accounts/password/change/` */
function PasswordForm() {
  const change = useChangePassword()

  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")

  const currentBlank = currentPassword.length === 0
  const newTooShort = newPassword.length < MIN_PASSWORD_LENGTH
  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword

  const disabled = change.isPending || currentBlank || newTooShort || mismatch

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (disabled) return
    try {
      await change.mutateAsync({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setCurrentPassword("")
      setNewPassword("")
      setConfirmPassword("")
    } catch {
      // Surfaced from `change.isError` below.
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle>Password</CardTitle>
          <CardDescription>
            Your current password is required. The new password is never sent
            back to the browser.
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="password-current">Current password</Label>
            <Input
              id="password-current"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password-new">New password</Label>
            <Input
              id="password-new"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
            {newTooShort && newPassword.length > 0 ? (
              <p role="alert" className="text-xs text-destructive">
                Use at least {MIN_PASSWORD_LENGTH} characters.
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                At least {MIN_PASSWORD_LENGTH} characters.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password-confirm">Confirm new password</Label>
            <Input
              id="password-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
            {mismatch ? (
              <p role="alert" className="text-xs text-destructive">
                The two new passwords do not match.
              </p>
            ) : null}
          </div>

          {change.isError ? (
            <ErrorNote message={normalizeApiError(change.error).message} />
          ) : null}
          {change.isSuccess ? (
            <SuccessNote message="Password changed." />
          ) : null}

          <Button type="submit" disabled={disabled}>
            {change.isPending ? "Changing…" : "Change password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

/**
 * One boolean preference, rendered as a toggle button.
 *
 * `components/ui` has no checkbox primitive, and a pressed button maps onto a
 * boolean more honestly than a styled `<div>` would. `role="switch"` +
 * `aria-checked` is what a screen reader actually needs here.
 */
function PreferenceToggle({
  id,
  label,
  description,
  checked,
  onToggle,
}: {
  id: string
  label: string
  description: string
  checked: boolean
  onToggle: () => void
}) {
  return (
    <div className="space-y-1">
      <Button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        variant={checked ? "default" : "outline"}
        onClick={onToggle}
        className="w-full justify-between"
      >
        <span>{label}</span>
        <span className="text-xs opacity-80">{checked ? "On" : "Off"}</span>
      </Button>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

/**
 * `GET/PUT /notifications/preferences/`
 *
 * Only the four fields `NotificationPreferenceSerializer` exposes are rendered.
 * `validate()` rejects `quiet_hours_start == quiet_hours_end`, so the form
 * blocks that pair itself rather than sending a request the server will refuse.
 *
 * The editable form is a separate component keyed on the preference id, so its
 * state initializer always has the loaded row and a background refetch of the
 * same row cannot clobber an edit in progress.
 */
function NotificationPreferencesSection() {
  const preferenceQuery = useNotificationPreference()

  if (preferenceQuery.isLoading) return <Skeleton className="h-56 w-full" />
  if (preferenceQuery.isError) {
    return (
      <Card>
        <CardContent className="pt-6">
          <ErrorNote
            message={normalizeApiError(preferenceQuery.error).message}
          />
        </CardContent>
      </Card>
    )
  }

  const preference = preferenceQuery.data
  if (!preference) return null

  return (
    <NotificationPreferencesForm key={preference.id} preference={preference} />
  )
}

/** The editable preferences form, seeded from the loaded row. */
function NotificationPreferencesForm({
  preference,
}: {
  preference: NotificationPreference
}) {
  const update = useUpdateNotificationPreference()

  const [emailEnabled, setEmailEnabled] = useState(preference.email_enabled)
  const [inAppEnabled, setInAppEnabled] = useState(preference.in_app_enabled)
  const [quietStart, setQuietStart] = useState(
    toTimeInputValue(preference.quiet_hours_start)
  )
  const [quietEnd, setQuietEnd] = useState(
    toTimeInputValue(preference.quiet_hours_end)
  )

  // `validate()` rejects an equal pair. Comparing the raw values is enough:
  // the two inputs are `HH:MM` and the server stores `HH:MM:SS`, so a genuine
  // equality is exact in both representations.
  const quietHoursEqual =
    quietStart.trim().length > 0 && quietStart.trim() === quietEnd.trim()

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (quietHoursEqual) return
    try {
      await update.mutateAsync({
        email_enabled: emailEnabled,
        in_app_enabled: inAppEnabled,
        quiet_hours_start: quietStart.trim() || null,
        quiet_hours_end: quietEnd.trim() || null,
      })
    } catch {
      // Surfaced from `update.isError` below; the toggles keep their state.
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle>Notification preferences</CardTitle>
          <CardDescription>
            How guidance notifications reach you, and when to hold them.
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <PreferenceToggle
            id="pref-email"
            label="Email notifications"
            description="Delivery to your account email address."
            checked={emailEnabled}
            onToggle={() => setEmailEnabled((current) => !current)}
          />

          <PreferenceToggle
            id="pref-in-app"
            label="In-app notifications"
            description="Delivery inside AEGIS."
            checked={inAppEnabled}
            onToggle={() => setInAppEnabled((current) => !current)}
          />

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="pref-quiet-start">Quiet hours start</Label>
              <Input
                id="pref-quiet-start"
                type="time"
                value={quietStart}
                onChange={(event) => setQuietStart(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pref-quiet-end">Quiet hours end</Label>
              <Input
                id="pref-quiet-end"
                type="time"
                value={quietEnd}
                onChange={(event) => setQuietEnd(event.target.value)}
              />
            </div>
          </div>

          {quietHoursEqual ? (
            <p role="alert" className="text-sm text-destructive">
              Quiet hours start and end must differ.
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Optional. Leave both blank for no quiet hours. The server rejects
              a start and end that are the same.
            </p>
          )}

          {update.isError ? (
            <ErrorNote message={normalizeApiError(update.error).message} />
          ) : null}
          {update.isSuccess ? (
            <SuccessNote message="Notification preferences saved." />
          ) : null}

          <Button type="submit" disabled={update.isPending || quietHoursEqual}>
            {update.isPending ? "Saving…" : "Save preferences"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

export function AccountSettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeading />
      <IdentityCard />
      <ProfileSection />
      <Separator />
      <PasswordForm />
      <Separator />
      <NotificationPreferencesSection />
    </div>
  )
}
