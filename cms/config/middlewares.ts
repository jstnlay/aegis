import type { Core } from '@strapi/strapi';

/**
 * SEC-006 — Strapi network/CORS hardening.
 *
 * AEGIS flow is Browser -> Django API -> Strapi. Strapi is an internal
 * CMS service: the admin panel is served same-origin and Django calls
 * Strapi server-side, where browser CORS never applies. No browser
 * origin needs cross-origin access to Strapi in normal operation.
 *
 * STRAPI_CORS_ORIGINS is the explicit allowlist of trusted browser
 * origins (comma-separated). If it is unset or empty:
 *   - in production, CORS fails closed: NO browser origin is granted
 *     (there is deliberately no wildcard fallback);
 *   - in development, only this project's own Django dev origins are
 *     trusted so local debugging stays practical.
 */
const DEVELOPMENT_DEFAULT_ORIGINS = [
  'http://localhost:8000', // Django dev server (the AEGIS browser-facing origin)
  'http://127.0.0.1:8000',
];

export default ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Middlewares => {
  const configuredOrigins = env.array('STRAPI_CORS_ORIGINS', []);
  const isProduction = process.env.NODE_ENV === 'production';
  const trustedOrigins =
    configuredOrigins.length > 0 ? configuredOrigins : isProduction ? [] : DEVELOPMENT_DEFAULT_ORIGINS;

  return [
    'strapi::logger',
    'strapi::errors',
    // Security headers (helmet) stay enabled with Strapi defaults.
    'strapi::security',
    {
      name: 'strapi::cors',
      config: {
        // Exact-match echo of trusted origins only. Returning '' blocks:
        // koa-cors then emits no Access-Control-* headers at all, so
        // browsers refuse cross-origin reads/preflights. Server-to-server
        // clients (Django) send no Origin header and are not subject to
        // browser CORS enforcement either way.
        origin: (ctx: { request?: { header?: Record<string, string | undefined> } }): string => {
          const requestOrigin = ctx.request?.header?.origin ?? '';
          if (!requestOrigin) {
            return '';
          }
          return trustedOrigins.includes(requestOrigin) ? requestOrigin : '';
        },
        // No browser client holds credentialed access to Strapi; keep
        // Access-Control-Allow-Credentials out of every response.
        credentials: false,
        // Minimal method set for CMS content reads. Content writes happen
        // through the same-origin admin panel or server-side via Django.
        methods: ['GET', 'HEAD', 'OPTIONS'],
        headers: ['Content-Type', 'Authorization', 'Origin', 'Accept'],
      },
    },
    // strapi::poweredBy intentionally removed: stop disclosing
    // "X-Powered-By: Strapi <version>" on responses.
    'strapi::query',
    'strapi::body',
    'strapi::session',
    'strapi::favicon',
    'strapi::public',
  ];
};
