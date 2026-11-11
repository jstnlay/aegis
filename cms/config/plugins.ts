import type { Core } from '@strapi/strapi';

const allowedMediaTypes = [
  'image/*',
  'video/*',
  'audio/*',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.*',
  'text/plain',
  'text/csv',
];

const deniedExecutableTypes = [
  'application/vnd.microsoft.portable-executable',
  'application/x-msdownload',
  'application/x-msdos-program',
  'application/x-executable',
  'application/x-dosexec',
  'application/x-sh',
  'text/x-shellscript',
  'application/x-mach-binary',
];

/**
 * Upload storage. The free Render plan has no persistent disk, so files
 * written to cms/public/uploads are lost on the next redeploy. When
 * Supabase Storage (S3-compatible) is configured, uploads go there and
 * survive redeploys instead.
 *
 * Fail closed to the local provider: if any of the S3 variables is
 * missing, this returns undefined and Strapi keeps using its local
 * filesystem provider, so an unconfigured deployment still boots and
 * existing local files keep serving. No provider is switched
 * unconditionally, and nothing deletes or rewrites existing files.
 *
 * Two details are specific to Supabase and were the reason an upload with
 * a complete configuration still failed with a 500:
 *
 * - the endpoint is addressed path-style, not virtual-host style;
 * - the bucket rejects the ACL header the provider sends by default, so
 *   `ACL` is present and undefined, which makes the provider leave the
 *   header off.
 *
 * The public base URL is what the stored file URL is built from, so the
 * browser loads the object straight from the bucket. It is derived from
 * the endpoint and can be overridden with SUPABASE_S3_PUBLIC_URL.
 */
const s3ProviderOptions = ({
  env,
}: Core.Config.Shared.ConfigParams): Record<string, unknown> | undefined => {
  const endpoint = env('SUPABASE_S3_ENDPOINT', '');
  const bucket = env('SUPABASE_S3_BUCKET', '');
  const accessKeyId = env('SUPABASE_S3_ACCESS_KEY', '');
  const secretAccessKey = env('SUPABASE_S3_SECRET_KEY', '');
  if (!endpoint || !bucket || !accessKeyId || !secretAccessKey) {
    return undefined;
  }
  return {
    credentials: { accessKeyId, secretAccessKey },
    region: env('SUPABASE_S3_REGION', 'ap-southeast-1'),
    endpoint,
    forcePathStyle: true,
    requestChecksumCalculation: 'WHEN_REQUIRED',
    params: { Bucket: bucket, ACL: undefined },
  };
};

/** The public URL the bucket serves its objects from. */
const s3PublicUrl = ({
  env,
}: Core.Config.Shared.ConfigParams): string | undefined => {
  const endpoint = env('SUPABASE_S3_ENDPOINT', '');
  const bucket = env('SUPABASE_S3_BUCKET', '');
  const explicit = env('SUPABASE_S3_PUBLIC_URL', '');
  if (explicit) {
    return explicit.replace(/\/+$/, '');
  }
  if (!endpoint || !bucket) {
    return undefined;
  }
  return `${endpoint.replace(/\/+$/, '').replace(/\/storage\/v1\/s3$/, '/storage/v1/object/public')}/${bucket}`;
};

const config = ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Plugin => {
  const providerOptions = s3ProviderOptions({ env });
  const publicUrl = s3PublicUrl({ env });
  return {
    'users-permissions': {
      config: {
        jwtManagement: 'refresh',
        sessions: {
          httpOnly: true,
        },
      },
    },
    upload: {
      config: {
        // Supabase Storage is S3-compatible; Django treats a non-Strapi
        // media origin as an authored external link (see
        // _safe_strapi_media_path), so nothing else changes downstream.
        ...(providerOptions
          ? {
              provider: 'aws-s3',
              providerOptions: {
                ...(publicUrl ? { baseUrl: publicUrl } : {}),
                s3Options: providerOptions,
              },
            }
          : {}),
        security: {
          allowedTypes: allowedMediaTypes,
          deniedTypes: deniedExecutableTypes,
        },
      },
    },
  };
};

export default config;
