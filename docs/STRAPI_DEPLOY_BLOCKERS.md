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

## 2. "Internal server error" / 502 when uploading a file in Strapi

State: content types, admin panel and the read API all work. Only media
writes fail, and they now surface as 502 — Render's proxy got no response
at all, i.e. the Strapi process crashed or restarted mid-upload. An S3
misconfiguration answers 500, not 502, so the ranked causes below should be
read with that in mind; the first `aegis-cms` log lines after a failed
upload decide between them (`Killed` / out of memory vs `NoSuchBucket` /
`AccessDenied` / `SignatureDoesNotMatch` vs `EACCES` / `ENOENT`).

Ranked causes, in the order worth checking:

1. **Supabase Storage misconfiguration.** The `aegis-cms` deploy now carries
   `cms/config/plugins.ts`, which switches the upload provider to `aws-s3`
   when `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_BUCKET`, `SUPABASE_S3_ACCESS_KEY`
   and `SUPABASE_S3_SECRET_KEY` are all set. Partial configuration falls
   back to the local provider, so a 500 means the four are set and one of
   them is wrong. The usual offenders: bucket does not exist, bucket is not
   public, keys are project API keys instead of Storage S3 access keys
   (Supabase -> Storage -> S3 access keys), or region is not what the
   endpoint signs with. Check the first error line in Render ->
   `aegis-cms` -> Logs: `NoSuchBucket`, `AccessDenied` or `SignatureDoesNotMatch`
   name the variable that is wrong.
2. **Local provider cannot write.** `cms/public/uploads/.gitkeep` is
   committed, so the directory exists in a fresh checkout; a write failure
   here appears as `EACCES`/`ENOENT` in the same log.
3. **Deploy predates the S3 change.** `git log origin/master -- cms/config/plugins.ts`
   shows the commit that landed. If `aegis-cms` last deployed before it, the
   provider is still local and cause 2 is the answer.

Fast isolation, given Render has no free shell: temporarily delete the four
`SUPABASE_S3_*` vars, redeploy, retry the upload. Local success proves the
provider switch is the variable at fault; local failure moves the cause to
the code or the image.

Known ceiling while this is open: free-plan Render has no persistent disk,
so even a working local upload is lost on the next redeploy. TC-ADM-14/15
cannot pass reliably until Supabase Storage works.

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
