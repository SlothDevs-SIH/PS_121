#!/bin/sh
# Writes the S3 identity file from environment variables, then starts SeaweedFS
# (master + volume + filer + S3 gateway in one process) with authentication enforced.
set -eu
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"
cat > /tmp/s3.json <<JSON
{"identities":[{"name":"smriti","credentials":[{"accessKey":"${S3_ACCESS_KEY}","secretKey":"${S3_SECRET_KEY}"}],"actions":["Admin","Read","Write","List","Tagging"]}]}
JSON
exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json -volume.max=0
