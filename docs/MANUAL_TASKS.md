# Manual tasks after the May-addition batch

Five things still need a human. Each section says what to do, where, and how
to tell it worked. The formula-driven Excel gradebook is deliberately not
here — that is a separate day's work.

---

## 1. Publish an announcement photo

**Why.** `cover_image` was added to the Strapi announcement content type. The
Strapi service applies content-type changes when it boots, so there is no
migration command to run — a redeploy is the migration.

**Do this**

1. Push to `master`. Render auto-deploys both services (`aegis` for Django,
   `aegis-cms` for Strapi; both track `master`, both `autoDeploy: true`).
   Watch the `aegis-cms` deploy log: the schema sync happens at boot.
2. Open the Strapi admin panel (the `aegis-cms` service's URL + `/admin`) →
   **Content Manager → Announcement** → open an entry → the **Cover image**
   media field → upload a photo → **Save** → **Publish**.
3. Check Django picked it up:
   `GET /api/v1/cms/announcements/` now carries a `cover_image` value. When the
   file is on the Strapi origin it is a proxy path
   `/api/v1/cms/announcements/{document_id}/image/`; the bytes are served by
   Django, never by a direct Strapi URL.
4. Look at the screens: `/app/student/announcements`,
   `/app/parent/announcements`, and **Admin → Content** (thumbnail column).
5. Publishing also fires the Strapi → Django webhook, so the targeted roles get
   a notification (Guidance & Parents → Notifications).

**If the photo does not appear**

- The Strapi service sleeps on the free tier; the first request after idle
  takes ~50 s. Retry once.
- Check the `aegis-cms` logs for the upload.
- Check the file really is in the Strapi Media Library.
- If the image is on Supabase Storage (task 2), Django treats the bucket URL
  as an authored external link and the browser loads it straight from the
  bucket — it must be public-read for that to work.

---

## 2. Make uploaded images survive a redeploy

**Why.** The free Render plan has no persistent disk, so anything written to
`cms/public/uploads` is lost on every redeploy — uploaded photos disappear.
`cms/config/plugins.ts` only switches the upload provider to S3 when **all
four** `SUPABASE_S3_*` values are set; otherwise it silently keeps the local
filesystem provider. The Django service has the same problem for profile
photos, and its settings switch to the bucket on the same variables.

**Do this**

1. In Supabase (same project as the CMS database): create a **public** bucket,
   e.g. `cms-uploads`, and create an S3 access key pair
   (Project Settings → API Keys → S3 keys). The endpoint is
   `https://<project-ref>.supabase.co/storage/v1/s3`.
2. Render dashboard → the **aegis-cms** service → **Environment** → add:

   | Key | Value |
   |---|---|
   | `SUPABASE_S3_ENDPOINT` | `https://<project-ref>.supabase.co/storage/v1/s3` |
   | `SUPABASE_S3_BUCKET` | `cms-uploads` |
   | `SUPABASE_S3_REGION` | the bucket's region, e.g. `ap-southeast-1` |
   | `SUPABASE_S3_ACCESS_KEY` | from step 1 |
   | `SUPABASE_S3_SECRET_KEY` | from step 1 |

   `render.yaml` already declares these five as `sync: false` — the values
   live only in the dashboard, never in the repository.
3. Render dashboard → the **aegis** service → **Environment** → add the same
   five. The Django service stores profile photos in the same bucket.
4. Save and redeploy both services.
5. Verify: upload a test photo in the Strapi admin, publish, then redeploy
   the service again. The photo must still be there afterwards.

**Why an upload with a complete configuration still failed before**

`cms/config/plugins.ts` now sends the request the way Supabase's S3 API
needs, and both details were the reason a 500 came back with all four values
set:

- the endpoint is addressed **path-style**, not virtual-host style, so the
  provider is configured with `forcePathStyle`;
- Supabase's bucket rejects the **ACL header** the provider sends by default,
  so `ACL` is present and undefined, which makes the provider leave it off.

The stored file URL is built from the public bucket URL, which the config
derives from the endpoint (`.../storage/v1/object/public/<bucket>`); set
`SUPABASE_S3_PUBLIC_URL` to override it.

**Two caveats worth knowing**

- Setting the keys is **additive**: uploads made before the switch keep their
  `/uploads/...` paths and are still lost on redeploy. Only new uploads go to
  the bucket.
- With the bucket in play, Django does not proxy those images (SEC-007 treats
  a foreign host as an authored external link). The browser loads them
  straight from the bucket, so the bucket has to be public-read — image
  visibility is not role-scoped for them.

---

## 3. Decide whether moderate risk reaches the adviser

**Why.** The implemented rule is the conservative one: guidance staff are
always notified; the section's adviser and the linked parents are notified
only on **HIGH**. If the instructor wants the adviser on MODERATE too, it is
two lines.

**Do this (only if the answer changes)**

1. `backend/aegis_backend/apps/guidance/views.py` —
   `RiskAlertViewSet.perform_create`, the line
   `if alert.risk_level == "high":` — that block adds the adviser **and** the
   parents. Split it: put the adviser under
   `if alert.risk_level in ("moderate", "high"):` and keep the parents under
   `"high"`.
2. `backend/aegis_backend/ai_engine/risk_service.py` —
   `integrate_risk_result`, the line `if current_level == "high":` — same
   split, for the automatic path.
3. Update `docs/AT_RISK_ACCESS_POLICY.md` (the table and the open-questions
   list) to match.
4. Update the tests: `apps.guidance.tests.RiskAlertCreateTest` —
   `test_manual_low_alert_notifies_guidance_only` asserts that a non-high
   alert reaches nobody but guidance. Add a moderate case.
5. Note the dedup: one notification per student per level per day
   (`risk_alert:<student>:<level>:<date>`), so a second alert of the same
   level the same day is not re-notified.

---

## 4. Give the forecast something to project

**Why.** The predictive mode projects a **monthly** series and refuses to
answer with fewer than three points — it says "No estimate yet" by design
rather than projecting from noise.

**Do this**

| Metric | What it needs |
|---|---|
| `grade_average` | Finalized grades in grading periods whose **end dates fall in three different months**. Admin → Academics sets the periods; then import or enter finalized grades. |
| `attendance_rate` | Attendance records dated in three different months. Import attendance files (Admin → Imports & Exports, or Faculty → Imports for your own sections). Sample files: `docs/test-data/attendance-*.csv`, `attendance-sf2-*.xlsm`. |
| `risk_alerts` | Risk alerts created in three different months — run the risk computation over a dataset with history, or create manual alerts in Guidance → Risk alerts. |

Then check: **Admin → Analytics → Predictive mode** → choose the range
(1/3/6/12 months) → **Refresh**. The card shows the estimate, the number of
months on record, and the first and last month of the series.

**Note.** The seeded DEV dataset usually covers one or two months, so the card
stays empty until real history exists. That is the intended behaviour, not a
fault.

---

## 5. Keep risk scores fresh

**Why.** `run_risk_computation` currently runs in the Django service's
**build command** (see `render.yaml`), so risk scores refresh on every
deploy — not on a schedule. Nothing re-scores a student between deploys.

**Do this**

1. Render dashboard → **New → Cron Job**:
   - Repo: the same repository, branch `master`.
   - Root directory: `backend/aegis_backend`.
   - Schedule: e.g. `0 6 * * *` (06:00 UTC daily).
   - Build command:
     `pip install -r ../requirements/production.txt && python manage.py migrate --settings=config.settings.development && python manage.py run_risk_computation --settings=config.settings.development`
   - Environment: the same variables the `aegis` web service has (database
     credentials at minimum).
2. The trained model is **not** a file on disk: `load_stored_model()` reads
   the active `RiskModelArtifact` from the database, and the deploy build
   already trains it. So the cron job needs no model file — only the
   database.
3. Verify: the command prints
   `Done: N processed, M actionable alerts, K insufficient-data.` Then open
   Guidance → Risk alerts and confirm the alerts are dated today.
4. Test first with `--dry-run` (computes without persisting or notifying).

**Guardrails already in place.** The command is idempotent: an unchanged risk
state does not create a duplicate alert, a manual alert is never overwritten
by a computed one, and a student with too little history is recorded as
`insufficient_data` rather than given an invented score.
