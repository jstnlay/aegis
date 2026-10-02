/**
 * Account settings API (PH11.8).
 *
 * Self-service only, and deliberately narrow. `UserProfileSerializer` is the
 * contract behind `GET/PATCH /accounts/me/`; `PasswordChangeView` handles
 * `POST /accounts/password/change/`.
 *
 * Nothing here reads or writes another user. `/accounts/users/` is
 * `IsAdminUser` and is deliberately not consumed, so an administrator's own
 * settings page uses exactly the same two endpoints as everyone else's.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { apiClient } from "@/lib/api"

/* -------------------------------------------------------------------------- */
/* Contract                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * `UserProfileSerializer` — `GET/PATCH /accounts/me/`.
 *
 * Read-only, server-controlled (SEC-001 remediation):
 *   - `email` and `username` are the login identity,
 *   - `role` and `is_active` are account state.
 *
 * None of those can be written through this serializer, so no mutation in this
 * module ever sends them. The four writable fields are the only ones the
 * settings form offers.
 */
export interface CurrentUser {
  id: string
  email: string
  username: string
  first_name: string
  last_name: string
  role: string
  phone_number: string | null
  address: string | null
  /**
   * `CharField(max_length=10, blank=True, null=True)` — a free-form field, not
   * a choice set, so the UI edits it as plain text rather than inventing a
   * language enum the backend does not define.
   */
  language_preference: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** `PATCH /accounts/me/` body. */
export interface UpdateProfilePayload {
  first_name: string
  last_name: string
  phone_number: string | null
  address: string | null
  language_preference: string | null
}

/**
 * `POST /accounts/password/change/` body.
 */
export interface ChangePasswordPayload {
  current_password: string
  /** `min_length=8`, plus the project's `validate_password` rules. */
  new_password: string
}

/* -------------------------------------------------------------------------- */
/* Notification preferences                                                    */
/* -------------------------------------------------------------------------- */

/**
 * `NotificationPreferenceSerializer` — `GET`/`PUT /notifications/preferences/`.
 *
 * The view is a `RetrieveUpdateAPIView` whose `get_object` does
 * `get_or_create(user=request.user)`, so the row always exists by the time it
 * is read and the client never has to create one.
 *
 * Exactly four writable fields, and the viewset exposes no others — the UI must
 * not offer a preference the serializer would reject.
 */
export interface NotificationPreference {
  id: string
  email_enabled: boolean
  in_app_enabled: boolean
  /** `HH:MM:SS` from a `TimeField`, or `null` for unset. */
  quiet_hours_start: string | null
  quiet_hours_end: string | null
}

/** `PUT /notifications/preferences/` body. */
export interface UpdateNotificationPreferencePayload {
  email_enabled: boolean
  in_app_enabled: boolean
  /** `HH:MM` or `HH:MM:SS`, or `null` to clear. */
  quiet_hours_start: string | null
  quiet_hours_end: string | null
}

const NOTIFICATION_PREFERENCE_KEY = ["notifications", "preferences"] as const

export function useNotificationPreference() {
  return useQuery<NotificationPreference, Error>({
    queryKey: NOTIFICATION_PREFERENCE_KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<NotificationPreference>(
        "/notifications/preferences/"
      )
      return data
    },
  })
}

/**
 * `PUT /notifications/preferences/`
 *
 * PUT rather than PATCH: the serializer validates `quiet_hours_start` against
 * `quiet_hours_end` in `validate()`, comparing the submitted value to the
 * stored instance value for whichever field was omitted. Sending the full set
 * makes that comparison the one the user actually sees in the form.
 *
 * `onSuccess` writes the server's response into the cache, so the saved state
 * is what the form re-renders from rather than the local draft.
 */
export function useUpdateNotificationPreference() {
  const queryClient = useQueryClient()
  return useMutation<
    NotificationPreference,
    Error,
    UpdateNotificationPreferencePayload
  >({
    mutationFn: async (payload) => {
      const { data } = await apiClient.put<NotificationPreference>(
        "/notifications/preferences/",
        payload
      )
      return data
    },
    onSuccess: (preference) => {
      queryClient.setQueryData(NOTIFICATION_PREFERENCE_KEY, preference)
    },
  })
}

const CURRENT_USER_KEY = ["accounts", "me"] as const

/* -------------------------------------------------------------------------- */
/* Queries                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * The signed-in user.
 *
 * A failure here is not cosmetic: the form is seeded from this response, so an
 * error must surface rather than render an empty editable form that would then
 * PATCH blank values over real data.
 */
export function useCurrentUser() {
  return useQuery<CurrentUser, Error>({
    queryKey: CURRENT_USER_KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<CurrentUser>("/accounts/me/")
      return data
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Mutations                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * `PATCH /accounts/me/`
 *
 * Invalidates the cached user so the header and the freshly saved form read the
 * server's response rather than the locally held draft.
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation<CurrentUser, Error, UpdateProfilePayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.patch<CurrentUser>(
        "/accounts/me/",
        payload
      )
      return data
    },
    onSuccess: (user) => {
      queryClient.setQueryData(CURRENT_USER_KEY, user)
    },
  })
}

/**
 * `POST /accounts/password/change/`
 *
 * The response is only `{ "detail": "Password changed." }`, and both passwords
 * are `write_only` — the new password is never echoed back. The mutation
 * therefore resolves to `void` and the caller clears the form itself rather
 * than trying to reconcile a user object that does not come back.
 */
export function useChangePassword() {
  return useMutation<void, Error, ChangePasswordPayload>({
    mutationFn: async (payload) => {
      await apiClient.post<{ detail: string }>(
        "/accounts/password/change/",
        payload
      )
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Field helpers                                                               */
/* -------------------------------------------------------------------------- */

/**
 * Normalizes an editable text field to the payload shape.
 *
 * `phone_number`, `address` and `language_preference` are all
 * `blank=True, null=True`, so an emptied field must be sent as `null` rather
 * than `""` — DRF treats the two differently on a `CharField`.
 */
export function optionalText(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}
