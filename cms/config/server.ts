import type { Core } from '@strapi/strapi';

const config = ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Server => ({
  // SEC-006: bind narrowly by default so Strapi stays an internal CMS
  // service. Production deployments that must accept external traffic
  // set HOST explicitly (e.g. behind a reverse proxy / private network).
  host: env('HOST', 'localhost'),
  port: env.int('PORT', 1337),
  app: {
    keys: env.array('APP_KEYS')!,
  },
  webhooks: {
    populateRelations: env.bool('WEBHOOKS_POPULATE_RELATIONS', false),
    // Shared secret sent with every outbound webhook. The AEGIS Django
    // backend verifies this header in constant time before processing.
    defaultHeaders: {
      'X-AEGIS-Webhook-Secret': env('AEGIS_WEBHOOK_SECRET', ''),
    },
  },
});

export default config;
