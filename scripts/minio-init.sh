#!/bin/sh
set -eu
: "${MINIO_ROOT_USER:?}"
: "${MINIO_ROOT_PASSWORD:?}"
: "${S3_ACCESS_KEY:?}"
: "${S3_SECRET_KEY:?}"
: "${S3_BUCKET:?}"
case "$S3_BUCKET" in *[!a-z0-9.-]*|'') echo 'Nome de bucket inválido' >&2; exit 1;; esac
attempt=0
until mc alias set studio http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1 && mc ready studio >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then echo 'MinIO não ficou pronto após 120s' >&2; exit 1; fi
  sleep 2
done
mc mb --ignore-existing "studio/$S3_BUCKET" >/dev/null
mc anonymous set none "studio/$S3_BUCKET" >/dev/null
mc version enable "studio/$S3_BUCKET" >/dev/null
mc admin user add studio "$S3_ACCESS_KEY" "$S3_SECRET_KEY" >/dev/null
policy_file=$(mktemp)
trap 'rm -f "$policy_file"' EXIT HUP INT TERM
printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:ListBucket","s3:GetBucketLocation"],"Resource":["arn:aws:s3:::%s"]},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":["arn:aws:s3:::%s/*"]}]}' "$S3_BUCKET" "$S3_BUCKET" > "$policy_file"
mc admin policy create studio ctf-studio-objects "$policy_file" >/dev/null
mc admin policy attach studio ctf-studio-objects --user "$S3_ACCESS_KEY" >/dev/null
echo 'Bucket privado pronto; credencial de aplicação restrita ao bucket.'
