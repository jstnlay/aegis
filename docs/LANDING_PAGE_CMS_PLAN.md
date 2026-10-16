# Landing page CMS plan (announcements + resources)

Written 2026-10-17, after the Strapi blockers closed. Status: plan only, no
code changed for this yet.

## Where things stand

The landing page was showing 502 for its content blocks because the backend
could not reach Strapi. That is fixed on the deployed stack (CMS reads 200,
webhook URL synced, media uploads work on the local provider). The local
stack still needs `manage.py migrate` (5 pending migrations) and a restart of
`runserver` with `STRAPI_BASE_URL=https://aegis-cms.onrender.com` and a valid
`STRAPI_API_TOKEN`; the token in `cms/.env` is stale (401) because it belongs
to the local Strapi database, so the value must come from the Render `aegis`
service.

## What the landing page already renders

`frontend/src/routes/pages/LandingPage.tsx` already has both CMS blocks, in
this order: hero, About, Mission/vision, "What AEGIS offers", Announcements,
Resources, FAQ, Contact.

- `AnnouncementsSection` (line 364) reads `usePublicAnnouncements()`
  (`GET /api/v1/cms/announcements/public/`) and renders one card per
  announcement with a type badge and published date.
- `ResourcesSection` (line 437) reads `usePublicResources()`
  (`GET /api/v1/cms/resources/public/`) and renders one row per resource with
  title, description and type badge.
- Both say "the content service is temporarily unavailable" on error rather
  than rendering an empty list (that is the 502 the user saw).

Strapi content types: `announcement` (draftAndPublish, target_roles,
expires_at; `cms/src/api/announcement/content-types/announcement/schema.json`)
and `resource` (file/url; `cms/src/api/resource/...`). There is **no
relation** between them today. Django proxies both through
`backend/aegis_backend/apps/cms/services/strapi_client.py`
(`list_announcements` line 333, `list_resources`, `get_announcement` line 311,
`get_resource` line 322) with normalizers and serializers; the public views
live in `apps/cms/views.py` / `urls.py`.

## The request, and the three readings

"Add announcement in landing page, then the resources inside" can mean three
different amounts of work. Pick one when awake; the plan lists all three so
no rereading is needed.

### Option 1 - content only, no code (5 minutes)

Publish the announcement and the resource in Strapi. The landing page already
shows both. This closes TC-ADM-12/13 (landing page feed) today.

### Option 2 - visually nest resources inside the announcements area (~30-45 minutes)

Frontend-only: merge the two sections so Announcements is the block and
Resources renders inside it (subheading + the existing list), instead of two
peer sections.

- File: `frontend/src/routes/pages/LandingPage.tsx` only.
- Tests: `frontend/src/routes/pages/school-identity.test.tsx` and
  `frontend/src/routes/routes.test.tsx` mock both hooks; update assertions if
  headings/ids move. Run `npm.cmd test` and `npm.cmd run build`.
- No backend, no Strapi change, no deploy risk.

### Option 3 - announcements carry their own resources (~2-3 hours)

Real relation: each announcement can list resources inside its card (files,
links, videos).

1. Strapi: add a `manyToMany` relation to both content types
   (`cms/src/api/announcement/content-types/announcement/schema.json` gains
   `resources`, `cms/src/api/resource/.../schema.json` gains `announcements`).
2. Django: `strapi_client.py` must request the relation
   (`params={"populate[resources][populate]": "file"}` on
   `list_announcements` / `get_announcement`), `normalize_announcement` must
   pass it through, and `apps/cms/serializers.py` must expose it (reusing the
   resource normalizer so media URLs stay handled the same way).
3. Frontend: `CmsAnnouncement` type in `frontend/src/features/admin/api.ts`
   gains `resources`; `AnnouncementsSection` renders each resource as a link.
4. Tests: `backend/aegis_backend/apps/cms/tests.py` (list/detail populate),
   `frontend/src/features/cms/public-api.test.tsx`, `routes.test.tsx`.
5. Deploy: `aegis-cms` restarts on push; content stays in the database, but
   remember that any push also wipes local-disk uploads (ephemeral) - do
   media retests before pushing.

Recommended split: Option 1 now (the page already works), then decide if
"resources inside" means Option 2 or Option 3. Option 3 is the only one that
puts a resource *inside a specific announcement*.

## Pending manual items (morning list)

1. Local backend: `migrate`, then `runserver` with the Render token + base
   URL, then reload the landing page. Fix: `backend/aegis_backend/.env`
   (gitignored) with `STRAPI_BASE_URL` and `STRAPI_API_TOKEN`.
2. Media retests (TC-ADM-12/13/14/15, 03/04/05/18, 17) **before any push** -
   a push redeploys `aegis-cms` and wipes uploaded files.
3. Re-upload the hero image and re-save the `announcement-test` entry (its
   image URL 404s).
4. Docs commit `a9f9e6f` (Strapi blocker ledger) is committed locally and
   held back; push it after the media retests.
5. Optional, for upload durability (TC-ADM-14/15): restore the four
   `SUPABASE_S3_*` variables with Supabase Storage -> S3 access keys, a
   public bucket, endpoint `https://<project-ref>.supabase.co/storage/v1/s3`
   and region `ap-southeast-1`.

## Verification gates

- Landing page change: `npm.cmd test` (frontend) and `npm.cmd run build`.
- Any Django serializer change: `manage.py test apps.cms
  --settings=config.settings.test`.
- Strapi schema change: `npx.cmd tsc --noEmit` in `cms/`, then one manual
  upload + publish check in the admin.
