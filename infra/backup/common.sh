# Shared helpers for backup.sh, restore.sh and verify.sh (sourced, not run).
# Everything goes through the running compose stack: `docker compose exec -T postgres` for the
# database tools, and a one-off rclone container on the stack's network for the S3 buckets.
# shellcheck shell=bash disable=SC2034  # the EXIT_* codes are used by the sourcing scripts

# Exit codes (the same in every script; each script uses its own subset).
readonly EXIT_USAGE=2         # bad arguments, or restore without --yes
readonly EXIT_PRECONDITION=3  # stack not running, tool missing, version mismatch, lock held
readonly EXIT_DATABASE=4      # pg_dump / pg_restore / psql failed
readonly EXIT_OBJECTS=5       # the S3 copy failed
readonly EXIT_VERIFY=6        # checksums or the dump's table of contents do not check out

# Pinned like every other image (backend plan V-B3; tests/unit/test_image_pins.py).
RCLONE_IMAGE=${RCLONE_IMAGE:-rclone/rclone:1.75@sha256:45401ad7410db1d67ffdb58e19059ad20b0d8e0285a60e38bbec55cc1019c7a5}

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPO_ROOT" || exit 3  # docker compose finds docker-compose.yml (and .env) here

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2; }
die() {
  local code=$1
  shift
  printf 'error: %s\n' "$*" >&2
  exit "$code"
}

# value "$@" (with $1 the option): the option's value, or a usage error (exit 2, where
# ${2:?} would exit 1). Use as var=$(value "$@"); set -e passes the exit code on.
value() {
  [[ $# -ge 2 && -n $2 && $2 != --* ]] || die "$EXIT_USAGE" "$1 needs a value"
  printf '%s' "$2"
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "$EXIT_PRECONDITION" "'$1' is required but not on PATH"
}

compose() { docker compose "$@"; }

# Container id of a running compose service, or fail with a hint.
running() {
  local id
  id=$(compose ps -q --status running "$1" 2>/dev/null || true)
  [[ -n $id ]] || die "$EXIT_PRECONDITION" "the '$1' service is not running (docker compose up -d $1)"
  printf '%s' "$id"
}

# Run a PostgreSQL client tool inside the postgres container as the database owner. PGUSER,
# PGDATABASE and PGPASSWORD come from the container's own environment, so nothing secret
# appears on this host's command line; pass -d to target another database.
pg() {
  # shellcheck disable=SC2016  # expanded by the container's shell, not this one
  compose exec -T postgres sh -c \
    'export PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" PGPASSWORD="$POSTGRES_PASSWORD"; exec "$@"' \
    sh "$@"
}

container_env() { compose exec -T "$1" printenv "$2"; }

sha256_file_list() {  # sha256 of each file given on stdin (NUL-separated), sha256sum format
  if command -v sha256sum >/dev/null 2>&1; then
    xargs -0 sha256sum
  else
    xargs -0 shasum -a 256
  fi
}

sha256_check() {  # verify a SHA256SUMS file in the current directory
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum --quiet -c SHA256SUMS
  else
    shasum -a 256 --quiet -c SHA256SUMS
  fi
}

# Path of a host directory as docker understands it (Git Bash on Windows: C:/...).
host_path() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

# The compose network the s3 service is on (the rclone container joins it).
s3_network() {
  local id
  id=$(running s3)
  docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$id" |
    head -n 1
}

# rclone <host-dir> <rclone args...>: run rclone against the stack's object store, with
# <host-dir> mounted at /backup. The S3 keys are read from the s3 container and handed over
# by variable name only (docker run -e NAME), so they are not visible in `ps`.
rclone() {
  local dir=$1
  shift
  local network
  network=$(s3_network)
  RCLONE_CONFIG_SMRITI_ACCESS_KEY_ID=$(container_env s3 S3_ACCESS_KEY)
  RCLONE_CONFIG_SMRITI_SECRET_ACCESS_KEY=$(container_env s3 S3_SECRET_KEY)
  export RCLONE_CONFIG_SMRITI_ACCESS_KEY_ID RCLONE_CONFIG_SMRITI_SECRET_ACCESS_KEY
  MSYS_NO_PATHCONV=1 docker run --rm --network "$network" \
    --user "$(id -u):$(id -g)" \
    -v "$(host_path "$dir"):/backup" \
    -e RCLONE_CONFIG=/dev/null \
    -e RCLONE_CONFIG_SMRITI_TYPE=s3 \
    -e RCLONE_CONFIG_SMRITI_PROVIDER=SeaweedFS \
    -e RCLONE_CONFIG_SMRITI_ENDPOINT=http://s3:8333 \
    -e RCLONE_CONFIG_SMRITI_ACCESS_KEY_ID \
    -e RCLONE_CONFIG_SMRITI_SECRET_ACCESS_KEY \
    -e XDG_CACHE_HOME=/tmp \
    "$RCLONE_IMAGE" "$@"
}

# key=value lookup in a backup's backup-info.txt.
info() { sed -n "s/^$2=//p" "$1/backup-info.txt" | head -n 1; }

# Checksums of every file in a backup directory against its SHA256SUMS manifest.
verify_checksums() {
  local dir=$1
  [[ -f $dir/SHA256SUMS ]] || die "$EXIT_VERIFY" "$dir has no SHA256SUMS manifest"
  log "checking $(wc -l <"$dir/SHA256SUMS" | tr -d ' ') checksums in $dir"
  (cd "$dir" && sha256_check) || die "$EXIT_VERIFY" "checksum mismatch in $dir (see above)"
  local listed actual
  listed=$(wc -l <"$dir/SHA256SUMS" | tr -d ' ')
  actual=$(cd "$dir" && find . -type f ! -name SHA256SUMS | wc -l | tr -d ' ')
  [[ $listed == "$actual" ]] ||
    die "$EXIT_VERIFY" "$dir holds $actual files but SHA256SUMS lists $listed"
}
