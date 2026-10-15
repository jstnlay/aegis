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
    region: env('SUPABASE_S3_REGION', 'us-east-1'),
    endpoint,
    params: { Bucket: bucket },
  };
};

const config = ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Plugin => {
  const providerOptions = s3ProviderOptions({ env });
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
