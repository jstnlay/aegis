# Open blockers — Strapi deploy (flagged 2026-10-16, not fixed yet)

Filed during the Cycle-2 CMS retest. Both issues need the Render dashboard
and are not fixable from the repository.

## 1. AEGIS CMS screens returned 502 (announcements and resources) — FIXED 2026-10-17

Cause: `STRAPI_BASE_URL` was unset on the `aegis` service, so
`StrapiClient` fell back to `http://localhost:1337`
(`backend/aegis_backend/config/settings/base.py:252`) and every CMS read
raised `StrapiUnavailableError` -> 502.

Fix applied in the Render dashboard: `STRAPI_BASE_URL`,
`STRAPI_API_TOKEN`, `STRAPI_WEBHOOK_SECRET` set on `aegis`, redeployed.

Verified 2026-10-17 from outside the deployment:

    curl https://aegis-0pav.onrender.com/api/v1/cms/announcements/public/
    -> 200 in 0.69s, {"count":2,"results":[{"document_id":"kjihhwtb..."}...]}

The Strapi admin (`https://aegis-cms.onrender.com/admin`) answers 200.
The webhook receiver is armed: a POST without the secret header returns
`401 Invalid webhook authentication.` (an unset secret would return 503).

## 2. Media uploads returned 500 / 520 — FIXED 2026-10-17 (local provider)

State: content types, admin panel and the read API all work. Only media
writes failed. The failure changed shape as causes were peeled off: "Internal
server error" -> 520 on a 183 KB PNG -> after the image-processing toggles
were switched off, a plain 500 for both images and PDFs.

Two independent causes, both fixed 2026-10-17:

1. **Image processing on the 512 MB free instance.** Strapi resizes every
   image into four breakpoints, then runs stats and size optimization. A
   183 KB PNG with a large raster killed the process mid-request — the
   proxy reports that as 520, which is why an image failed differently from
   a PDF. Fixed in the admin, no deploy: Admin -> Settings -> Media Library
   -> turn OFF "Responsive friendly upload" and "Size optimization" (and
   "Auto orientation" / "AI metadata" if shown). Those are database-stored
   plugin settings, so they survive redeploys; turning them back on
   reintroduces the crash on large images.
2. **The Supabase Storage provider.** All four `SUPABASE_S3_*` variables
   were set, and at least one value was wrong — with a complete but bad
   configuration every upload is rejected by S3 and surfaces as 500, for
   images and PDFs alike. Removing the four variables switched
   `cms/config/plugins.ts` back to the local filesystem provider and
   uploads succeeded. The classic wrong value is a project API key
   (`anon`/`service_role`) instead of a Storage -> S3 access key.

Known ceiling while S3 stays unset: the local provider writes to Render's
ephemeral disk, so uploaded files are lost on every redeploy, and any push
to master redeploys `aegis-cms` and wipes them — do media retests before
pushing. The `announcement-test` entry still points at
`/uploads/BACKGROUND_01a2c51ffe.png`, which 404s; re-upload that image and
save the announcement again. TC-ADM-14/15 need real durability: re-add the
four variables with values from Supabase (bucket exists and is Public,
access keys from Storage -> S3 access keys, endpoint
`https://<project-ref>.supabase.co/storage/v1/s3`, region `ap-southeast-1`),
then re-upload.

## 3. Strapi webhook pointed at a dead hostname — FIXED in code 2026-10-17

State: the `AEGIS Django` webhook stored in Strapi targeted
`https://aegis-backend.onrender.com/webhooks/strapi/announcements/`. That
hostname resolves to Render's edge but no service answers on it (150s
timeout on the root path, twice); the live Django service answers on
`https://aegis-0pav.onrender.com` (200 on the public feed). The admin
webhook form also refused the correct URL with "url must be a valid URL",
so the UI was a dead end.

Root cause: `cms/src/index.ts` `ensureWebhook()` created the webhook only
when one with the same name did not exist, and returned without comparing
anything when it did. A webhook created by hand (or by an earlier deploy)
therefore kept its stale URL forever. The deploy environment
(`AEGIS_WEBHOOK_URL` on `aegis-cms`) never reached it.

Fix: `ensureWebhook()` now treats `AEGIS_WEBHOOK_URL` as the source of
truth on every boot — if the existing webhook's URL differs, or it is
disabled, or `entry.publish` is missing from its events, it is updated in
place. When `AEGIS_WEBHOOK_URL` is unset the existing row is left alone
(only the localhost default is used for first creation). The secret header
itself is global, from `cms/config/server.ts` `webhooks.defaultHeaders`
(`AEGIS_WEBHOOK_SECRET`), so only the two env vars on `aegis-cms` matter.

Verify after the next `aegis-cms` deploy: the boot log contains
`[aegis] Updated webhook "AEGIS Django" -> https://aegis-0pav.onrender.com/webhooks/strapi/announcements/`,
and a publish in the admin produces a 200 on the Django receiver.
