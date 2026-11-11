# Who may read student records, and who is told about at-risk students

Answers `NEED-TO-APPLY-AND-CHECK-May-Addition.md` §11 (the psychology
instructor's question) and records the policy the code implements.

## Read access to guidance records

| Record | Guidance | Faculty | Student | Parent |
|---|---|---|---|---|
| Behavioral notes | all | own sections | own | linked children |
| Consultations | own caseload | — | own | linked children |
| Risk alerts | all | own sections | own | linked children |
| Interventions | own caseload | — | — | — |
| Student profile | all | own sections | — | — |
| Grades | all | own subjects **+ advisees' subjects** | own | linked children |
| Attendance | all | own sections | own | linked children |

The scope lives in each viewset's `get_queryset`, not in the client. Every
read of a sensitive record also writes an `ACCESS` audit event, so "who
looked at this student" is answerable afterwards.

The one deliberate widening: an adviser sees **every subject grade** of the
students in their advisory section, not only the subjects they teach
themselves. That is the adviser's job, and it is still limited to the
sections they advise.

## Who is notified about an at-risk student

One rule, for automatic and manual alerts alike:

- **Guidance staff** — always notified.
- **The section's adviser** and **the linked parents** — notified when the
  risk level is **high**.

The automatic path is `ai_engine/risk_service.py` (`integrate_risk_result`).
The manual path is `RiskAlertViewSet.perform_create` in
`apps/guidance/views.py`, which uses the same recipients and the same
daily deduplication key (`risk_alert:<student>:<level>:<date>`), so a manual
alert and an automatic alert on the same day do not double-notify.

Notification delivery honours each recipient's own preferences (in-app and
email) in `apps/notifications/events.py`.

## Consent

`ConsentRecord` (`apps/accounts`) records a parent's consent for the school
to view identifiable student records. It is readable by admin and by the
parent who granted it, and it is not what gates guidance access — guidance
access is scoped by role and section, as in the table above.

## Open items for the instructor

- Whether the adviser should also be notified on **moderate** risk, and
  whether parents should be notified below high. The current rule is the
  conservative one.
- Whether the daily deduplication key is the right granularity: a second
  manual alert for the same student on the same day is not re-notified.
