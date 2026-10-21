# Sign-in without weakening role-based access

Source: `docs/capstone/Final_Revision.pdf` (163 pages), "User Design Interface"
and the non-functional requirements. Implementation: Django + DRF (SimpleJWT)
backend, React frontend, five-role access model.

## Status

| Piece | State |
| --- | --- |
| Remember me (document element 3) | **Built.** The login form carries the checkbox, the flag reaches `POST /api/v1/auth/login/`, and the refresh token is issued with the idle lifetime (15 min) or the remembered one (1 day). Backend and frontend tests cover both. |
| Idle session: 15 minutes | **Built.** Access token 15 min, refresh token 15 min without the checkbox. |
| Health / readiness probes | **Built.** `/health`, `/ready` and `/api/v1/health/`, `/api/v1/ready/`. |
| Password reset | **Built.** `POST /api/v1/accounts/password/forgot/` (enumeration-safe, 5/min per IP) mails a single-use hashed token that lives 30 minutes; `POST /api/v1/accounts/password/reset/` sets the password, clears the onboarding flag, revokes every outstanding refresh token and writes an audit row. Screens: `/forgot-password`, `/reset-password`. |
| Student registration | **Built.** `RegistrationRequest` table (no role, no permissions). `POST /api/v1/accounts/registrations/` (enumeration-safe, 5/min per IP) hashes the password and mails a 24-hour verification link; `GET .../registrations/verify/?token=` confirms the address; the admin queue at `/accounts/admin/registrations/` approves (naming the section, creating the user and the student profile in one transaction) or rejects. Screen: `/register`. |
| Parent invitation | **Built.** `ParentInvitation` table. A student nominates a parent from the student dashboard (a request, no account); the admin queue approves, which mints the 7-day invitation token and mails the link; the parent accepts at `/accept-invitation`, which creates the parent account and the `ParentStudentLink` in one transaction. |
| Staff set-password link | **Built.** `POST /accounts/users/create/` takes the password optionally: without one the account is created with an unusable password, `must_change_password` set, and a 24-hour set-password link is emailed to the person. No administrator chooses a colleague's password and none travels by email. The link redeems through the same primitive as the password reset (`/set-password`). |
| Sign up link, Register screen | Planned (Part E). |


## What the documentation asks for

`Final_Revision.pdf` pages 90-91 (document pages 77-78) specify the
Login and Register screens element by element:

**Login** — (1) Email textbox, (2) Password textbox (masked), (3) *Remember Me*
checkbox, (4) *Forgot Password* link, (5) Login button, (6) *Sign Up* link.

**Register** — (7) Name textbox, (8) Email textbox, (9) Password textbox,
(10) Confirm Password textbox, (11) Sign Up button, (12) Login link.

Related requirements in the same document:

- NFR-006 — no duplicate registration with the same email address.
- NFR-008 — passwords are hashed before storage.
- NFR-009 — students see and modify only their own data.
- NFR-010 — administrators see student data only aggregated or anonymized
  unless consent is recorded.
- NFR-011 — role-based access control: users reach only what their role allows.
- NFR-005 — the dashboard loads within 5 seconds of login.
- NFR-015 — usable from 320 px to 1920 px.
- Page 69 — "Role-based access control will be implemented … Authentication
  and session management will be handled through Laravel Breeze."

Two notes on that last line. The stack named there (Laravel Breeze) is not the
stack this system is built in; what the document is actually specifying is a
conventional sign-in surface with a persistent-session option and a
password-recovery path. The intent is kept, the implementation stays in
Django + SimpleJWT + React.

## What exists today

| Piece | State |
| --- | --- |
| Sign in | `/login`, email + password, returns a JWT pair. No Remember me, no Forgot password, no Sign up link. |
| First password change | `/change-password`, forced for provisioned accounts via `must_change_password`. |
| Registration | None. Accounts are created by an administrator (`UserCreateView`) or by the QA provisioning command. |
| Password recovery | None. |
| Sessions | 30-minute access token, 7-day refresh token, rotation on refresh, blacklist on logout. |
| Client storage | `localStorage` (`aegis.access_token`, `aegis.refresh_token`). The password is never stored. |
| Throttles | login 15/min per IP, refresh 30/min per IP, password change 10/min per account. |
| Roles | `User.role` — student, parent, faculty, guidance, admin. Server-controlled: no serializer writes it. |

The documentation's Login screen is therefore three elements short, and the
Register screen does not exist.

## The principle

**Authentication proves who you are. Authorization decides what you can do.**
Adding a sign-in path must not add a way to choose a role.

Four rules follow, and they are what keeps the role model intact:

1. A self-registered account gets **no role**. It is a request, not a member.
2. Only an administrator turns a request into an account, and the role is the
   administrator's choice, never the applicant's.
3. Every authenticated request still resolves through the same `User.role`
   field and the same permission classes. No new path bypasses them.
4. Nothing in the registration or recovery flow can read or write a student or
   parent record.

The trap to avoid: giving `User.role` a default, or a `"self_registered"`
value that some permission class later treats as "student". A role that is
not one of the five is a hole in the model, and holes get filled by accident.

## Part A — Registration (the Sign Up screen)

**Students only.** A student registers for themselves; the account is still
approved by an administrator before it can sign in. Parents, faculty and
guidance do not self-register — see Part A2 and Part A3.

**Do not create a `User` row on registration.** Create a
`RegistrationRequest` row instead.

| Field | Purpose |
| --- | --- |
| `email` | unique; the account identifier once approved |
| `full_name` | document element (7) |
| `password_hash` | hashed at submission, never stored in plaintext |
| `account_type` | `student` or `parent` — the *kind* of account, not a role grant |
| `student_reference` | optional: the student code a parent is registering for |
| `status` | `pending` / `verified` / `approved` / `rejected` |
| `verification_token_hash`, `verification_expires_at` | single-use email verification |
| `reviewed_by`, `reviewed_at`, `review_note` | who decided, and when |
| `privacy_policy_accepted_at` | the document's privacy terms, already tracked on the user |
| `created_at` | ordering and sweeping |

Why a separate table: a `User` without a role breaks the invariant that every
user has one, and a `User` with a role grants access the moment it is created.
A request has no permissions at all, so it cannot be escalated by a bug in
the approval code — the worst case is a request that is never approved.

**Endpoints**

- `POST /api/v1/accounts/registrations/` — public, throttled 5/min per IP.
  Always answers `202` with the same body whether the address is new,
  already registered, or unknown. A duplicate email is refused quietly
  (NFR-006) and the applicant is told to sign in or contact the office.
- `GET /api/v1/accounts/registrations/{token}/verify/` — email link. Marks
  the request `verified` and mails the administrators.
- `GET /api/v1/admin/registrations/` — `IsAdminUser`. The review queue.
- `POST /api/v1/admin/registrations/{id}/approve/` — `IsAdminUser`. The
  administrator picks the role and, for a student, links the `StudentProfile`;
  for a parent, links the `ParentProfile` and the `ParentStudentLink`.
- `POST /api/v1/admin/registrations/{id}/reject/` — `IsAdminUser`.

**Approval reuses the existing account-creation path.** The approve action
calls the same code that `UserCreateView` uses today (create the user, create
the profile, link the parent, set `must_change_password=True`, write the
audit event). One code path means one set of rules: the self-lockout guard,
the audit trail and the profile-link rules are not re-implemented for
registrations.

**Verification before review.** The applicant proves they own the address
before an administrator spends time on it. Unverified requests older than N
days are swept by a management command, and the same command can sweep
rejected ones.

**A pending request signs in to nothing.** It has no `User`, so there is no
token to carry and no endpoint that accepts one. The confirmation email
links to a status page that shows "waiting for approval" — a public page
that reads the request by its token, not an authenticated screen.

## Part A2 — Parents: invitation, not open registration

**Open self-registration is the wrong shape for parents**, and the reason is
the data, not the paperwork. A parent's account reveals a child's grades,
attendance, guidance records and behavioural notes. With an open sign-up
form, anyone can type a child's name and code and land in the
administrator's approval queue, and the queue is trivially easy to flood —
the school ends up verifying stranger-submitted claims by telephone, one
request at a time, forever.

So a parent account is created from a school-side fact about the
relationship, not from a self-asserted claim. Three steps, three owners:

1. **The student nominates.** A student can name a parent (name, email,
   relationship) from their own profile. This is the channel for the parent
   the office has no phone number for. It creates a pending nomination, not an
   account.
2. **The administrator approves.** The admin verifies the nomination against
   the enrolment record — the school already holds the parent's contact
   details — and issues the invitation. The admin is the only actor who can
   move a parent request forward, the same as for a student registration.
3. **The parent accepts.** The invitation email carries a single-use code.
   The parent sets their own password; accepting creates the `ParentProfile`
   **and** the `ParentStudentLink` the invitation names, atomically. The
   role is granted by the invitation, which the administrator approved — the
   parent never selects it.

**Who invites:** the administrator issues it. The student's nomination is
the request, not the invitation. A nomination that no administrator acts on
never becomes an account, exactly like a student registration.

**Model** — `ParentInvitation`: `email`, `full_name`, `relationship`,
`student` (the `StudentProfile` the link will name), `nominated_by` (the
student, nullable when the office issues it directly), `status`
(`pending` / `approved` / `accepted` / `expired` / `revoked`), `token_hash`,
`expires_at`, `approved_by`, `approved_at`.

**Invitation token**: single use, hashed, 7 days (a parent may not open the
mail the same afternoon), consumed on acceptance, revocable by the admin.

**The existing enrolment record is the source of truth.** The admin issues
the invitation from the parent details already held there, so the flow adds
no new paperwork for the office.

## Part A3 — Faculty and guidance: provisioned, like an administrator

No self-registration. The administrator creates the account, exactly as
today — but the temporary password is never emailed.

**Set-password link.** The admin creates the account with
`must_change_password=True` and the system emails the teacher or counselor
a one-time, hashed, 24-hour set-password link. The person sets their own
password when they follow it, and `must_change_password` clears. The
existing onboarding gate in `core/authentication.py` then has nothing left to
do, because there is no temporary password to change.

**One mechanism, three callers.** The set-password token is the same
primitive used for password reset and for parent invitation acceptance. It
is one model, one expiry policy per use, one audit event shape — not three
near-copies of "email someone a link".

## Part B — Remember me, and the idle session

Not "store the password". It means: a longer session when the box is ticked.

- `POST /api/v1/auth/login/` accepts `remember_me`.
- **Idle session (box unticked): 15 minutes.** The access token lives 15
  minutes and the refresh token lives 15 minutes, so a browser left alone is
  signed out after a quarter of an hour. The client already refreshes
  silently on a 401, so an *active* user never notices.
- **Remember me (box ticked): 1 day.** The refresh token lives 24 hours; the
  access token still lives 15 minutes, because a long session must never
  mean a long-lived access token.
- Logout blacklists the refresh token, so "remember me" still ends the moment
  the user signs out.
- The client stores exactly what it stores today — the token pair, never the
  password. "Stay signed in" *is* the refresh lifetime.

Implementation: `SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] = 15 minutes` and
`REFRESH_TOKEN_LIFETIME = 1 day` (the remember-me ceiling). A login without
`remember_me` shortens the refresh token's own `exp` to 15 minutes, so one
serializer issues both lifetimes from one setting.

The checkbox is document element (3). It is a session-lifetime choice, not a
trust decision: it changes how long a stolen refresh token is worth.

## Part C — Forgot password

**Delivery: email, through the school's SMTP.** That is the only self-service
path. There is no second, weaker channel — no password over the phone, no
"tell the office your new password" — because a password that a human reads
out is a password that ends up on paper.

- `POST /api/v1/accounts/password/forgot/` — public, throttled 5/min per IP.
  Always answers the same thing, so it cannot be used to discover which
  addresses have accounts.
- The reset token: 32+ random bytes, stored **hashed**, single use, 30-minute
  expiry, replaced (not reused) by a newer request, invalidated on use.
  Model `PasswordResetToken`.
- The email carries a link to `/reset-password?token=…`. The page works
  without a session, like `/change-password` does today.
- `POST /api/v1/accounts/password/reset/` — token, new password, confirm.
  Runs the Django password validators, sets the password, clears
  `must_change_password`, **revokes every outstanding refresh token for that
  account** (the blacklist app is already in the project), and writes an
  audit event. A password reset must kill a session that was stolen with the
  old password.
- Throttle: 10/min per account on the reset attempt.
- **Fallback for a family with no working email:** the office uses the same
  admin screen to issue a set-password link (Part A3). Same primitive, same
  audit trail, and no temporary password is ever sent to anyone.

## Part D — How the role model is protected, item by item

| Risk | Answer |
| --- | --- |
| Registrant sets their own role | The registration serializer has no role field at all, so a crafted payload is ignored. |
| Registrant becomes a student and reads records | Approval is the only path to a `User`, and it is `IsAdminUser` plus the existing account-creation path. |
| Pending account reaches a protected endpoint | It has no `User` and therefore no token. |
| Reset flow leaks student data | The reset endpoints touch only the account: no student, parent or enrollment row is read. |
| Registration is used to enumerate accounts | Every public answer is identical; the duplicate-email case is refused quietly. |
| Approval is a silent privilege grant | It writes the same audit event as any other role change, with the acting administrator and the target. |
| Parent registration implies consent | It does not. The existing consent record flow still decides that (NFR-010). |
| New endpoints bypass the scoped querysets | They do not. Every role-scoped queryset and object-level check is untouched. |

## Part E — Frontend screens

All at 390-wide-first, in the school identity, matching the document's
elements one for one.

- `/login` — add *Remember me* (3), *Forgot password* (4), *Sign up* (6) to
  the existing email and password fields. A `remember_me` flag goes with the
  login request; the response tells the client which lifetime it received.
- `/register` — name (7), email (8), password (9), confirm password (10),
  sign up button (11), login link (12).
- `/forgot-password` — email, "check your inbox".
- `/reset-password?token=…` — new password, confirm, sign in.
- `/registration-status?token=…` — "waiting for approval", and the
  administrator's decision when it comes.
- The landing page's **Sign in** button already points at `/login`.

## Part F — What does not change

- No new role. `User.role` keeps exactly five values.
- No new permission class, no change to `IsStudentOwnData`,
  `IsParentOfStudent`, `IsFacultyOwnerOfGrade`, `IsAdminUser` or the admin
  aggregate rule.
- No change to token signing, refresh rotation, the `must_change_password`
  gate, the audit trail, or the role-specific dashboards and their scoping.

## Part G — Implementation order

1. **Model and migration** — `RegistrationRequest`, `PasswordResetToken`,
   `DEFAULT_FROM_EMAIL`, the two refresh lifetimes in settings.
2. **Backend** — registration submit/verify, admin review, password
   forgot/reset, `remember_me` on login, and a throttle scope for each.
3. **Email** — one small templated module (verification, reset, approved,
   rejected), plain text and HTML, school branding, no PII beyond name and
   address.
4. **Frontend** — the four screens plus the admin review panel inside the
   existing admin Users screen.
5. **Tests** — backend: registration cannot set a role; a pending request
   reaches no protected endpoint; the reset token is single-use and expires;
   every public answer is enumeration-safe; `remember_me` changes the
   lifetime and nothing else. Frontend: the login screen carries all six
   documented elements; register validation; the expired-token screen.
6. **Documentation** — correct the "Laravel Breeze" line and describe the
   sign-in flow as built.

## Part H — Decisions, settled

| Question | Decision |
| --- | --- |
| Who approves registrations? | The administrator. One approver for students and for parent invitations. |
| Who registers? | Students only. |
| How do parents get an account? | Invitation, issued by the administrator; the student may nominate a parent, which the administrator then approves and turns into an invitation. The parent never chooses a role — accepting the invitation creates the `ParentProfile` and the `ParentStudentLink` it names. (Part A2.) |
| Who invites? | The administrator. A student nomination is a request, never an invitation. |
| How do faculty and guidance get accounts? | Provisioned by the administrator like any other staff account, with a one-time set-password link instead of an emailed temporary password. (Part A3.) |
| Password reset delivery | School SMTP, single self-service channel. No password is ever read out or emailed in plaintext. The admin set-password link is the fallback for a family with no email. |
| Idle session | 15 minutes — access token and refresh token both 15 minutes. |
| Remember me | 1 day — refresh token 24 hours, access token still 15 minutes. |
| Password reset token | 30 minutes, single use. |
| Student registration verification email | 24 hours. |
| Parent invitation | 7 days. |
| Set-password link (staff) | 24 hours. |
