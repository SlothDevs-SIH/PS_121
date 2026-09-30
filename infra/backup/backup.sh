#!/usr/bin/env bash
# SMRITI backup: the PostgreSQL/TimescaleDB database (pg_dump, custom format) and every bucket
# of the SeaweedFS object store, into one timestamped directory with a SHA256SUMS manifest.
# Old backups beyond --keep are deleted. Needs the stack's postgres and s3 services running.
#
#   infra/backup/backup.sh [--dir DIR] [--keep N]
#
# DIR defaults to $SMRITI_BACKUP_DIR or <repo>/backups; N to $SMRITI_BACKUP_KEEP or 7.
# Exit codes: 0 ok, 2 usage, 3 precondition, 4 database dump, 5 object copy, 6 verification.
# See infra/backup/README.md (RPO/RTO, schedule, restore drill).
set -euo pipefail
# shellcheck source=infra/backup/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

usage() { sed -n '2,10s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; }

backup_dir=${SMRITI_BACKUP_DIR:-$REPO_ROOT/backups}
keep=${SMRITI_BACKUP_KEEP:-7}
while (($#)); do
  case $1 in
    --dir) backup_dir=$(value "$@"); shift 2 ;;
    --keep) keep=$(value "$@"); shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) usage >&2; die "$EXIT_USAGE" "unknown argument: $1" ;;
  esac
done
[[ $keep =~ ^[1-9][0-9]*$ ]] || die "$EXIT_USAGE" "--keep must be a whole number >= 1 (got '$keep')"

need docker
running postgres >/dev/null
running s3 >/dev/null
mkdir -p "$backup_dir"
backup_dir=$(cd "$backup_dir" && pwd)
# The default directory is inside the repository: keep the dumps out of git.
if [[ $backup_dir == "$REPO_ROOT/backups" && ! -e $backup_dir/.gitignore ]]; then
  printf '*\n' >"$backup_dir/.gitignore"
fi

# One backup at a time (mkdir is atomic on every OS, unlike flock).
lock=$backup_dir/.backup.lock
mkdir "$lock" 2>/dev/null ||
  die "$EXIT_PRECONDITION" "another backup is running (or crashed): remove $lock if not"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
final=$backup_dir/smriti-$stamp
work=$backup_dir/.smriti-$stamp.partial
done_ok=false
cleanup() {
  if [[ $done_ok != true ]]; then
    rm -rf -- "$work"
    log "backup failed; nothing was kept"
  fi
  rmdir -- "$lock" 2>/dev/null || true
}
trap cleanup EXIT
mkdir -p "$work/s3"

# 1. Database first, objects second: the stored objects are write-once, so every object the
#    dump refers to already exists when the bucket copy starts (objects added in between are
#    harmless extras). pg_dump reads one consistent snapshot while the API keeps running.
#    TimescaleDB's documented procedure: a plain pg_dump -Fc of the whole database (its
#    catalog and chunks included); pg_dump's warnings about circular foreign keys between
#    hypertables and chunks are expected. The restore needs the same TimescaleDB version,
#    so the versions go into backup-info.txt.
db=$(container_env postgres POSTGRES_DB)
log "dumping database '$db'"
pg pg_dump --format=custom --compress=6 --no-password >"$work/postgres.dump" ||
  die "$EXIT_DATABASE" "pg_dump failed"
[[ -s $work/postgres.dump ]] || die "$EXIT_DATABASE" "pg_dump wrote an empty file"
extensions=$(pg psql -X -At -v ON_ERROR_STOP=1 \
  -c "SELECT string_agg(extname || '=' || extversion, ',' ORDER BY extname) FROM pg_extension") ||
  die "$EXIT_DATABASE" "could not read the extension versions"
server=$(pg psql -X -At -c "SHOW server_version") || die "$EXIT_DATABASE" "could not read the server version"
log "database dump: $(wc -c <"$work/postgres.dump" | tr -d ' ') bytes"

# 2. Every bucket, copied object by object through the S3 API (the store stays online).
buckets=$(rclone "$work/s3" lsf --dirs-only smriti: | tr -d '/\r' | sort) ||
  die "$EXIT_OBJECTS" "could not list the buckets"
[[ -n $buckets ]] || die "$EXIT_OBJECTS" "the object store has no buckets (was bootstrap run?)"
counts=()
for bucket in $buckets; do
  log "copying bucket '$bucket'"
  mkdir -p "$work/s3/$bucket"  # an empty bucket is still restored
  rclone "$work/s3" copy --s3-no-check-bucket --stats-one-line --stats=30s \
    "smriti:$bucket" "/backup/$bucket" || die "$EXIT_OBJECTS" "copying bucket '$bucket' failed"
  counts+=("$bucket=$(find "$work/s3/$bucket" -type f | wc -l | tr -d ' ')")
done

# 3. What was backed up, from what, then the manifest over every file.
{
  echo "format=smriti-backup-1"
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_commit=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "database=$db"
  echo "server_version=$server"
  echo "extensions=$extensions"
  echo "timescaledb=$(tr ',' '\n' <<<"$extensions" | sed -n 's/^timescaledb=//p')"
  echo "postgres_image=$(docker inspect -f '{{.Config.Image}}' "$(running postgres)")"
  echo "s3_image=$(docker inspect -f '{{.Config.Image}}' "$(running s3)")"
  echo "buckets=$(tr '\n' ',' <<<"$buckets" | sed 's/,$//')"
  echo "objects=$(IFS=,; echo "${counts[*]}")"
} >"$work/backup-info.txt"
(cd "$work" && find . -type f -print0 | LC_ALL=C sort -z | sha256_file_list >SHA256SUMS) ||
  die "$EXIT_VERIFY" "writing SHA256SUMS failed"
verify_checksums "$work"

mv -- "$work" "$final"
done_ok=true
log "backup complete: $final"

# 4. Retention: keep the newest $keep complete backups (names sort by time).
find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name 'smriti-[0-9]*T[0-9]*Z' |
  LC_ALL=C sort -r | tail -n +$((keep + 1)) |
  while IFS= read -r dir; do
    log "retention (keep $keep): deleting $dir"
    rm -rf -- "$dir"
  done
printf '%s\n' "$final"
