#!/usr/bin/env bash
# SMRITI restore: put a backup made by backup.sh back into the running stack. DESTRUCTIVE: the
# database is dropped and re-created from the dump, and each backed-up bucket is made
# identical to the backup (objects that are not in the backup are deleted).
#
#   infra/backup/restore.sh [--db NAME] [--no-db] [--no-s3] --yes BACKUP_DIR
#
# Without --yes it only checks the backup and prints what it would overwrite. --db restores
# into another database (a restore drill that leaves the live one alone; combine with --no-s3).
# Exit codes: 0 ok, 2 usage or no --yes, 3 precondition, 4 database, 5 objects, 6 verification.
set -euo pipefail
# shellcheck source=infra/backup/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

usage() { sed -n '2,10s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; }

yes=false restore_db=true restore_s3=true target_db="" src=""
while (($#)); do
  case $1 in
    --yes) yes=true; shift ;;
    --db) target_db=$(value "$@"); shift 2 ;;
    --no-db) restore_db=false; shift ;;
    --no-s3) restore_s3=false; shift ;;
    -h | --help) usage; exit 0 ;;
    -*) usage >&2; die "$EXIT_USAGE" "unknown option: $1" ;;
    *) [[ -z $src ]] || die "$EXIT_USAGE" "one backup directory only"; src=$1; shift ;;
  esac
done
[[ -n $src ]] || { usage >&2; die "$EXIT_USAGE" "which backup? (a smriti-<timestamp> directory)"; }
[[ -d $src && -f $src/backup-info.txt ]] || die "$EXIT_USAGE" "$src is not a backup made by backup.sh"
[[ $restore_db == true || $restore_s3 == true ]] || die "$EXIT_USAGE" "--no-db and --no-s3: nothing to do"
src=$(cd "$src" && pwd)

need docker
running postgres >/dev/null
running s3 >/dev/null
verify_checksums "$src"

live_db=$(container_env postgres POSTGRES_DB)
target_db=${target_db:-$live_db}
[[ $target_db =~ ^[a-z_][a-z0-9_]*$ ]] || die "$EXIT_USAGE" "--db: use lower-case letters, digits and _"
buckets=$(info "$src" buckets | tr ',' ' ')

# The dump can only be restored by the TimescaleDB version that wrote it.
if [[ $restore_db == true ]]; then
  [[ -f $src/postgres.dump ]] || die "$EXIT_VERIFY" "$src has no postgres.dump"
  want=$(info "$src" timescaledb)
  have=$(pg psql -X -At -c \
    "SELECT default_version FROM pg_available_extensions WHERE name = 'timescaledb'" | tr -d '\r')
  [[ -n $want && $want == "$have" ]] || die "$EXIT_PRECONDITION" \
    "the backup needs TimescaleDB $want but the postgres service has '$have': run the image in $src/backup-info.txt"
fi

# App containers that hold connections to the live database are stopped for the restore and
# started again afterwards (not for a drill into another database).
stop=()
if [[ $restore_db == true && $target_db == "$live_db" ]]; then
  project=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$(running postgres)")
  for svc in api worker stream api-jwt api-oidc; do
    while IFS= read -r id; do
      [[ -n $id ]] && stop+=("$id")
    done < <(docker ps -q --filter "label=com.docker.compose.project=$project" \
      --filter "label=com.docker.compose.service=$svc")
  done
fi

echo "Backup:   $src"
echo "          made $(info "$src" created_at) from commit $(info "$src" git_commit)"
echo "This will OVERWRITE:"
if [[ $restore_db == true ]]; then
  echo "  - database '$target_db' on the postgres service: DROPPED and re-created from postgres.dump"
fi
if [[ $restore_s3 == true ]]; then
  for bucket in $buckets; do
    echo "  - bucket '$bucket': made identical to the backup (objects not in it are DELETED)"
  done
  echo "    (other buckets are left alone)"
fi
if ((${#stop[@]})); then
  echo "  - stopping ${#stop[@]} app container(s) meanwhile: $(docker inspect -f '{{.Name}}' "${stop[@]}" | tr -d '/' | tr '\n' ' ')"
fi
if [[ $yes != true ]]; then
  echo
  die "$EXIT_USAGE" "refusing to restore without --yes"
fi

if ((${#stop[@]})); then
  log "stopping app containers"
  docker stop "${stop[@]}" >/dev/null
fi
# Every failure ends in `die` (exit), which an ERR trap never sees: the hint is an EXIT trap.
restored=false
restart_hint() {
  if [[ $restored != true ]] && ((${#stop[@]})); then
    printf 'restore failed; the app containers stay stopped. Start them with: docker start %s\n' \
      "${stop[*]}" >&2
  fi
}
trap restart_hint EXIT

if [[ $restore_db == true ]]; then
  # TimescaleDB's procedure: a fresh database, the extension first, timescaledb_pre_restore()
  # (stops background jobs, sets the restoring flag), pg_restore of the whole dump, then
  # timescaledb_post_restore() - also after a failed pg_restore, so the database is never
  # left in restoring mode. One job: parallel pg_restore is not supported with TimescaleDB.
  log "re-creating database '$target_db'"
  printf '%s\n' 'DROP DATABASE IF EXISTS :"db" WITH (FORCE);' 'CREATE DATABASE :"db";' |
    pg psql -X -q -v ON_ERROR_STOP=1 -v db="$target_db" -d postgres ||
    die "$EXIT_DATABASE" "could not re-create database '$target_db'"
  pg psql -X -q -v ON_ERROR_STOP=1 -d "$target_db" \
    -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()" >/dev/null ||
    die "$EXIT_DATABASE" "timescaledb_pre_restore() failed"
  log "restoring postgres.dump into '$target_db'"
  status=0
  pg pg_restore --no-password -d "$target_db" <"$src/postgres.dump" || status=$?
  pg psql -X -q -v ON_ERROR_STOP=1 -d "$target_db" -c "SELECT timescaledb_post_restore()" >/dev/null ||
    die "$EXIT_DATABASE" "timescaledb_post_restore() failed"
  ((status == 0)) || die "$EXIT_DATABASE" "pg_restore reported errors (exit $status, see above)"
  pg psql -X -q -d "$target_db" -c "ANALYZE" || log "ANALYZE failed (the planner statistics are stale)"
fi

if [[ $restore_s3 == true ]]; then
  for bucket in $buckets; do
    [[ -d $src/s3/$bucket ]] || die "$EXIT_VERIFY" "$src/s3/$bucket is missing"
    log "restoring bucket '$bucket'"
    rclone "$src/s3" mkdir "smriti:$bucket" || die "$EXIT_OBJECTS" "could not create bucket '$bucket'"
    rclone "$src/s3" sync --s3-no-check-bucket --stats-one-line --stats=30s \
      "/backup/$bucket" "smriti:$bucket" || die "$EXIT_OBJECTS" "restoring bucket '$bucket' failed"
  done
fi

restored=true
if ((${#stop[@]})); then
  log "starting the app containers again"
  docker start "${stop[@]}" >/dev/null
fi
log "restore complete from $src (check: curl -sf http://127.0.0.1:8000/readyz)"
