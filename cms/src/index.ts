import fs from 'node:fs';
import path from 'node:path';

const AEGIS_WEBHOOK_NAME = 'AEGIS Django';
const AEGIS_API_TOKEN_NAME = 'AEGIS Backend';
/**
 * Operator-provided token from the service environment. On Render the
 * runtime filesystem is ephemeral, so a token written into cms/.env does
 * not survive a redeploy; the durable copy must live in the env vars.
 */
const ENV_API_TOKEN = process.env.STRAPI_API_TOKEN || '';
/**
 * Minimal read scope the Django backend needs for server-to-server CMS
 * access. These actions are intentionally NOT granted to the Strapi
 * public role: anonymous clients must go through Django's /api/v1/cms/
 * proxy so role/visibility filtering stays authoritative in Django.
 */
const CMS_READ_ACTIONS = [
  'api::announcement.announcement.find',
  'api::announcement.announcement.findOne',
  'api::resource.resource.find',
  'api::resource.resource.findOne',
];

/**
 * Persist a key=value pair into the project .env file so the AEGIS
 * Django backend can read server-side-only credentials (e.g. the
 * API token created here). Never logged, never printed.
 */
function upsertEnvFile(key: string, value: string) {
  const envPath = path.join(process.cwd(), '.env');
  let lines: string[] = [];
  if (fs.existsSync(envPath)) {
    lines = fs.readFileSync(envPath, 'utf8').split(/\r?\n/);
  }
  const prefix = `${key}=`;
  const idx = lines.findIndex((line) => line.startsWith(prefix));
  if (idx >= 0) {
    if (lines[idx] === prefix + value) return;
    lines[idx] = prefix + value;
  } else {
    lines.push('', `# AEGIS Phase 7 integration (shared with Django backend)`, prefix + value);
  }
  fs.writeFileSync(envPath, lines.join('\n'), 'utf8');
}

/**
 * Ensure the public role has NO CMS read access. Anonymous clients must
 * consume CMS content through Django's /api/v1/cms/ proxy (which enforces
 * role/visibility rules), never by querying Strapi directly. Django
 * itself reads via the server-side API token, so no public grants exist.
 * Idempotent: removes any previously granted CMS read permissions.
 */
async function revokePublicCmsReadAccess(strapi: any) {
  const publicRole = await strapi.db
    .query('plugin::users-permissions.role')
    .findOne({ where: { type: 'public' } });
  if (!publicRole) {
    strapi.log.warn('[aegis] Public role not found; skipping REST permission cleanup.');
    return;
  }
  for (const action of CMS_READ_ACTIONS) {
    const existing = await strapi.db
      .query('plugin::users-permissions.permission')
      .findMany({ where: { action, role: publicRole.id } });
    for (const permission of existing) {
      await strapi.db
        .query('plugin::users-permissions.permission')
        .delete({ where: { id: permission.id } });
      strapi.log.info(`[aegis] Revoked public REST access: ${action}`);
    }
  }
}

/**
 * Ensure the "AEGIS Backend" API token exists with the minimum practical
 * privilege: a Strapi "custom" content-API token limited to the CMS read
 * actions Django needs (no write/admin access). An existing broader
 * token (e.g. full-access) is downgraded in place, which preserves its
 * access key so cms/.env and the Django backend keep working.
 * Lifespan stays unlimited on purpose: an expiring token would silently
 * break the local/dev server-to-server workflow.
 */
async function ensureApiToken(strapi: any) {
  const existing = await strapi.db
    .query('admin::api-token')
    .findOne({ where: { name: AEGIS_API_TOKEN_NAME } });
  if (existing) {
    strapi.log.info('[aegis] API token "AEGIS Backend" already exists.');
    if (!ENV_API_TOKEN) {
      strapi.log.warn(
        '[aegis] Set the STRAPI_API_TOKEN service env var to this token: on Render, cms/.env does not survive a redeploy, so Django loses access on the next deploy.'
      );
    }
    if (existing.type !== 'custom') {
      await strapi.service('admin::api-token').update(existing.id, {
        type: 'custom',
        permissions: CMS_READ_ACTIONS,
      });
      strapi.log.info(
        '[aegis] API token "AEGIS Backend" restricted to custom read-only scope.'
      );
    }
    return;
  }
  const token = await strapi.service('admin::api-token').create({
    name: AEGIS_API_TOKEN_NAME,
    description: 'Server-to-server read-only access for the AEGIS Django backend (Phase 7)',
    type: 'custom',
    permissions: CMS_READ_ACTIONS,
    lifespan: null,
  });
  if (token?.accessKey) {
    upsertEnvFile('STRAPI_API_TOKEN', token.accessKey);
    // shortcut: the raw key is logged once, at creation, because Render's
    // runtime filesystem is ephemeral and cms/.env is lost on the next
    // redeploy — without this line the operator cannot copy the token into
    // the service env vars. Upgrade: delete both lines once
    // STRAPI_API_TOKEN is confirmed set in the Render env vars.
    strapi.log.warn(`[aegis] STRAPI_API_TOKEN=${token.accessKey}`);
    strapi.log.warn(
      '[aegis] Copy this token into the STRAPI_API_TOKEN env var of the Strapi and Django Render services.'
    );
    strapi.log.info('[aegis] Created API token "AEGIS Backend" and stored it in cms/.env.');
  } else {
    strapi.log.warn(
      '[aegis] API token created but raw accessKey was not returned; create one manually in Admin > Settings > API Tokens.'
    );
  }
}

async function ensureWebhook(strapi: any) {
  // The deploy environment is the source of truth for the URL when set;
  // the localhost value is only a local-dev default for first creation.
  const configuredUrl = process.env.AEGIS_WEBHOOK_URL || '';
  const url = configuredUrl || 'http://localhost:8000/webhooks/strapi/announcements/';
  const secret = process.env.AEGIS_WEBHOOK_SECRET || '';
  if (!secret) {
    strapi.log.warn(
      '[aegis] AEGIS_WEBHOOK_SECRET is not set: the Django webhook receiver rejects every event with a 500.'
    );
  }
  const existing = await strapi.db
    .query('strapi::webhook')
    .findMany({ where: { name: AEGIS_WEBHOOK_NAME } });
  if (existing.length > 0) {
    // A webhook created by hand, or by an earlier deploy, would otherwise
    // keep a stale URL (or stay disabled) forever: this function used to
    // return here without comparing anything.
    const current = existing[0];
    if (
      configuredUrl &&
      (current.url !== configuredUrl ||
        current.enabled !== true ||
        !Array.isArray(current.events) ||
        !current.events.includes('entry.publish'))
    ) {
      await strapi.db.query('strapi::webhook').update({
        where: { id: current.id },
        data: { url: configuredUrl, events: ['entry.publish'], enabled: true },
      });
      strapi.log.info(`[aegis] Updated webhook "${AEGIS_WEBHOOK_NAME}" -> ${configuredUrl}`);
    } else {
      strapi.log.info('[aegis] Webhook "AEGIS Django" already exists.');
    }
    return;
  }
  await strapi.db.query('strapi::webhook').create({
    data: {
      name: AEGIS_WEBHOOK_NAME,
      url,
      headers: {},
      events: ['entry.publish'],
      enabled: true,
    },
  });
  strapi.log.info(`[aegis] Created webhook "${AEGIS_WEBHOOK_NAME}" -> ${url}`);
}

export default {
  register(/* { strapi }: { strapi: Core.Strapi } */) {},

  async bootstrap({ strapi }: { strapi: any }) {
    try {
      await revokePublicCmsReadAccess(strapi);
    } catch (err) {
      strapi.log.error('[aegis] Failed to revoke public REST permissions:', err);
    }
    try {
      await ensureApiToken(strapi);
    } catch (err) {
      strapi.log.error('[aegis] Failed to ensure API token:', err);
    }
    try {
      await ensureWebhook(strapi);
    } catch (err) {
      strapi.log.error('[aegis] Failed to ensure webhook registration:', err);
    }
  },
};
