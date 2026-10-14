import { ChoiceField, Field } from "@/components/ui/form-field"
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
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  USER_ROLES,
  USER_ROLE_LABELS,
  useAdminUsers,
  useCreateUser,
  useUpdateUser,
  type AdminUser,
  type UpdateUserPayload,
  type UserRole,
} from "@/features/admin/api"
import { useAuth } from "@/features/auth/AuthContext"
import { normalizeApiError } from "@/lib/error"
import { ErrorNote } from "@/components/feedback/Feedback"

/**
 * User administration.
 *
 * The contract is list, retrieve, create and — as of PH11 — update:
 * `PATCH /accounts/users/{id}/` accepts exactly `role` and `is_active`, which
 * is what the Cycle-2 log recorded as "Not implemented" under TC-ADM-10. The
 * edit dialog therefore offers those two controls and nothing else.
 *
 * What is deliberately *not* offered still matters as much as what is. The
 * server rejects a change to your own account (self-lockout has no
 * self-service recovery), so the dialog disables editing for the signed-in
 * administrator rather than letting the request fail. There is no delete and
 * no password-reset route anywhere in the project, so neither is offered —
 * rendering a disabled button for them would suggest a capability the backend
 * does not have, and rendering an enabled one would simply fail.
 *
 * `email` is the login identity and stays read-only (SEC-001), and profile
 * fields remain the account owner's own `/accounts/me/` surface: posting them
 * here is ignored by `AdminUserUpdateSerializer`.
 */
/** A stable empty-array identity, so the `useMemo` below can depend on it. */
const EMPTY_USERS: readonly AdminUser[] = []

export function AdminUsersPage() {
  const usersQuery = useAdminUsers()
  const [roleFilter, setRoleFilter] = useState<UserRole | "all">("all")
  const [search, setSearch] = useState("")

  const users = useMemo(() => usersQuery.data ?? EMPTY_USERS, [usersQuery.data])
  const term = search.trim().toLowerCase()
  const filtered = useMemo(
    () =>
      users.filter((user) => {
        if (roleFilter !== "all" && user.role !== roleFilter) return false
        if (!term) return true
        return [user.email, user.first_name, user.last_name]
          .join(" ")
          .toLowerCase()
          .includes(term)
      }),
    [users, roleFilter, term]
  )

  const { pagination, pageRows } = useDataTablePagination(
    filtered,
    15,
    `users:${roleFilter}:${term}`
  )

  const columns: readonly DataTableColumn<AdminUser>[] = [
    {
      key: "name",
      header: "Name",
      cell: (user) => (
        <div className="min-w-0">
          <div className="font-medium">
            {[user.first_name, user.last_name].filter(Boolean).join(" ") || "—"}
          </div>
          <div className="text-xs text-muted-foreground">{user.email}</div>
        </div>
      ),
    },
    {
      key: "role",
      header: "Role",
      cell: (user) => (
        <Badge variant="secondary" data-user-role={user.role}>
          {USER_ROLE_LABELS[user.role] ?? user.role}
        </Badge>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (user) => (
        <Badge variant="outline" data-user-active={String(user.is_active)}>
          {user.is_active ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    {
      key: "created",
      header: "Created",
      cell: (user) => (
        <span className="text-sm text-muted-foreground">
          {formatDate(user.created_at)}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Access</span>,
      cell: (user) => <EditUserDialog user={user} />,
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-bold text-foreground">Users</h2>
        <p className="text-sm text-muted-foreground">
          Every account in the system — create one, and assign or withdraw its
          role and sign-in access from its row.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>Accounts</CardTitle>
              <CardDescription>
                Showing {filtered.length} of {users.length} accounts.
              </CardDescription>
            </div>
            <NewUserDialog />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="admin-users-role">Role</Label>
              <Select
                value={roleFilter}
                onValueChange={(value) =>
                  setRoleFilter(value as UserRole | "all")
                }
              >
                <SelectTrigger id="admin-users-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All roles</SelectItem>
                  {USER_ROLES.map((role) => (
                    <SelectItem key={role} value={role}>
                      {USER_ROLE_LABELS[role]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="admin-users-search">Search</Label>
              <Input
                id="admin-users-search"
                type="search"
                value={search}
                placeholder="Name or email"
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>

          <DataTable
            caption="User accounts"
            columns={columns}
            rows={pageRows}
            rowKey={(user) => user.id}
            isLoading={usersQuery.isLoading}
            error={
              usersQuery.isError
                ? normalizeApiError(usersQuery.error).message
                : null
            }
            loadingLabel="Loading user accounts"
            emptyMessage={
              term || roleFilter !== "all"
                ? "No accounts match the current filters."
                : "No user accounts exist yet."
            }
            pagination={pagination}
          />
        </CardContent>
      </Card>
    </div>
  )
}

function NewUserDialog() {
  const create = useCreateUser()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    role: "student" as UserRole,
    password: "",
  })

  const canSubmit =
    form.email.trim().length > 0 &&
    form.first_name.trim().length > 0 &&
    form.last_name.trim().length > 0 &&
    form.password.length >= 8

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New account</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create an account</DialogTitle>
          <DialogDescription>
            `POST /accounts/users/create/`. The role is chosen here because this
            is where the account's shape is decided; revise it later with "Edit
            access" on the account's row.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                email: form.email.trim(),
                // `username` is a real required field on UserCreateSerializer
                // even though email is the USERNAME_FIELD; the backend's own
                // SEC-001 tests post an empty string.
                username: "",
                first_name: form.first_name.trim(),
                last_name: form.last_name.trim(),
                role: form.role,
                password: form.password,
              },
              {
                onSuccess: () => {
                  setOpen(false)
                  setForm({
                    email: "",
                    first_name: "",
                    last_name: "",
                    role: "student",
                    password: "",
                  })
                },
              }
            )
          }}
        >
          {/*
            PH11.11: the four mandatory fields now go through the shared
            `Field`/`ChoiceField`, which is the pattern PH11.2 §16.5 asks for.

            Previously every field here was a bare `<Label>` + `<Input>` pair:
            the labels were bound, but nothing said a field was mandatory. The
            only signal was a disabled submit button with no stated reason, so a
            user who focused "Email", typed nothing and tabbed on found an inert
            button and no way to learn what was missing. Required-ness is now
            carried by `aria-required` on each control and by a visible asterisk,
            and the password hint is referenced by `aria-describedby` rather
            than sitting beside the field as an unassociated paragraph.
          */}
          <Field
            label="Email"
            id="new-user-email"
            type="text"
            value={form.email}
            onChange={(value) => setForm({ ...form, email: value })}
            required
          />

          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="First name"
              id="new-user-first-name"
              value={form.first_name}
              onChange={(value) => setForm({ ...form, first_name: value })}
              required
            />
            <Field
              label="Last name"
              id="new-user-last-name"
              value={form.last_name}
              onChange={(value) => setForm({ ...form, last_name: value })}
              required
            />
          </div>

          <ChoiceField
            label="Role"
            id="new-user-role"
            value={form.role}
            onChange={(value) => setForm({ ...form, role: value as UserRole })}
            options={USER_ROLES.map((role) => ({
              value: role,
              label: USER_ROLE_LABELS[role],
            }))}
          />

          <Field
            label="Initial password"
            id="new-user-password"
            // `password`, as it was as a hand-rolled `<Input>`. Admitting this form
            // to the shared `Field` must not have silently unmasked the field.
            type="password"
            value={form.password}
            onChange={(value) => setForm({ ...form, password: value })}
            required
            // Mirrors UserCreateSerializer's min_length=8.
            hint="At least 8 characters. The backend validates it against the project password rules."
          />

          {create.isError ? (
            <ErrorNote message={normalizeApiError(create.error).message} />
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit || create.isPending}>
              {create.isPending ? "Creating…" : "Create account"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Revise an account's role and active state.
 *
 * `PATCH /accounts/users/{id}/` takes only those two fields, so the form
 * offers no name, email or password controls it could not actually change —
 * profile fields remain their owner's `/accounts/me/` surface.
 *
 * The signed-in administrator's own row is not editable. The server refuses
 * that change outright because self-lockout has no self-service recovery, and
 * offering a form that can only ever fail would be worse than offering none.
 */
function EditUserDialog({ user }: { user: AdminUser }) {
  const { user: me } = useAuth()
  const update = useUpdateUser()
  const [open, setOpen] = useState(false)
  const [role, setRole] = useState<UserRole>(user.role)
  const [active, setActive] = useState(user.is_active)

  const displayName =
    [user.first_name, user.last_name].filter(Boolean).join(" ") || user.email

  if (me?.id === user.id) {
    return <span className="text-xs text-muted-foreground">Your account</span>
  }

  const dirty = role !== user.role || active !== user.is_active

  const close = () => {
    setOpen(false)
    setRole(user.role)
    setActive(user.is_active)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) setOpen(true)
        else close()
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          Edit access
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Access for {displayName}</DialogTitle>
          <DialogDescription>
            `PATCH /accounts/users/{user.id}/`. Only the role and the active
            flag can be changed here — email and profile fields belong to the
            account's owner. Every change is written to the audit log.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!dirty) return
            const patch: UpdateUserPayload = {}
            if (role !== user.role) patch.role = role
            if (active !== user.is_active) patch.is_active = active
            update.mutate(
              { userId: user.id, patch },
              {
                onSuccess: () => {
                  close()
                },
              }
            )
          }}
        >
          <ChoiceField
            label="Role"
            id={`edit-user-role-${user.id}`}
            value={role}
            onChange={(value) => setRole(value as UserRole)}
            options={USER_ROLES.map((option) => ({
              value: option,
              label: USER_ROLE_LABELS[option],
            }))}
            hint="Takes effect on the account's next request; nothing already signed in keeps the old permissions."
          />

          <ChoiceField
            label="Account status"
            id={`edit-user-status-${user.id}`}
            value={active ? "active" : "inactive"}
            onChange={(value) => setActive(value === "active")}
            options={[
              { value: "active", label: "Active — can sign in" },
              {
                value: "inactive",
                label: "Inactive — blocked from signing in",
              },
            ]}
          />

          {update.isError ? (
            <ErrorNote message={normalizeApiError(update.error).message} />
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" disabled={!dirty || update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}
