# Open blockers — Strapi deploy (flagged 2026-10-16, not fixed yet)

Filed during the Cycle-2 CMS retest. Both issues need the Render dashboard
and are not fixable from the repository.

## 1. AEGIS CMS screens return 502 (announcements and resources)

Evidence, measured from outside the deployment:

    curl https://aegis-0pav.onrender.com/api/v1/cms/announcements/public/
    -> {"detail":"Content service is temporarily unavailable."}
    HTTP 502, 0.26s

    curl -g https://aegis-cms.onrender.com/api/announcements?pagination[pageSize]=1
    -> 403   (0.25s, anonymous blocked by design)
    curl https://aegis-cms.onrender.com/admin
    -> 200   (Strapi itself is up and answering)

Diagnosis: Strapi is healthy. The Django service is refusing in a quarter
second, which is the signature of an unreachable base URL rather than a
slow upstream — `STRAPI_BASE_URL` is still unset on the `aegis` service, so
`StrapiClient` falls back to `http://localhost:1337`
(`backend/aegis_backend/config/settings/base.py:252`) and every CMS read
raises `StrapiUnavailableError` -> 502. `apps/cms/views.py` returns 502 only
for that class of error; a wrong token would surface as a different code.

Fix, in order:

1. Render -> `aegis` -> Environment -> confirm all three exist with values:
   `STRAPI_BASE_URL=https://aegis-cms.onrender.com`,
   `STRAPI_API_TOKEN` (the AEGIS Backend token),
   `STRAPI_WEBHOOK_SECRET`.
2. Manual Deploy (or Save Changes, which redeploys). Env var edits do not
   apply to a running process.
3. Verify: the curl above returns 200 with `{"results": ...}`. Admin Content
   screen, landing page feed, and the webhook all depend on this one change.

## 2. "Internal server error" when uploading a file in Strapi

State: content types, admin panel and the read API all work. Only media
writes fail.

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
