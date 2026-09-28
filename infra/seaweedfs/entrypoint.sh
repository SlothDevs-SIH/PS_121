#!/bin/sh
# Writes the S3 identity file from environment variables, then starts SeaweedFS
# (master + volume + filer + S3 gateway in one process) with authentication enforced.
set -eu
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"
cat > /tmp/s3.json <<JSON
{"identities":[{"name":"smriti","credentials":[{"accessKey":"${S3_ACCESS_KEY}","secretKey":"${S3_SECRET_KEY}"}],"actions":["Admin","Read","Write","List","Tagging"]}]}
JSON
# Small volumes + an explicit slot count: SeaweedFS's defaults (30 GB volumes, slots sized
# from free disk) let the first bucket take every slot on small disks, so later buckets
# could not store anything (found in B1: page images failed with 'no free volumes').
exec weed server -dir=/data -master.volumeSizeLimitMB=512 -volume.max=64 \
  -s3 -s3.port=8333 -s3.config=/tmp/s3.json
