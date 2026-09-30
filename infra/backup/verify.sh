#!/usr/bin/env bash
# SMRITI backup check: read-only, changes nothing. The SHA256SUMS manifest must match every
# file, the dump's table of contents must be readable (pg_restore --list, no database
# connection) and hold the app's tables, and each bucket listed in backup-info.txt must be there.
#
#   infra/backup/verify.sh BACKUP_DIR
#
# Needs the stack's postgres service running (for its pg_restore); it is only used as a tool.
# Exit codes: 0 ok, 2 usage, 3 precondition, 6 verification failed.
set -euo pipefail
# shellcheck source=infra/backup/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

usage() { sed -n '2,9s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; }

case ${1:-} in
  -h | --help) usage; exit 0 ;;
  "" | -*) usage >&2; die "$EXIT_USAGE" "which backup? (a smriti-<timestamp> directory)" ;;
esac
(($# == 1)) || die "$EXIT_USAGE" "one backup directory only"
src=$1
[[ -d $src && -f $src/backup-info.txt ]] || die "$EXIT_USAGE" "$src is not a backup made by backup.sh"
src=$(cd "$src" && pwd)
[[ $(info "$src" format) == smriti-backup-1 ]] || die "$EXIT_VERIFY" "unknown backup format in $src"

verify_checksums "$src"

need docker
running postgres >/dev/null
[[ -s $src/postgres.dump ]] || die "$EXIT_VERIFY" "$src has no postgres.dump"
toc=$(compose exec -T postgres pg_restore --list <"$src/postgres.dump") ||
  die "$EXIT_VERIFY" "pg_restore cannot read postgres.dump"
# The migration history, the well register and a hypertable: a dump of an empty or foreign
# database fails here.
for table in alembic_version well rt_sample; do
  grep -Eq "TABLE (DATA )?public $table " <<<"$toc" ||
    die "$EXIT_VERIFY" "postgres.dump has no table '$table'"
done
grep -q "EXTENSION - timescaledb" <<<"$toc" || die "$EXIT_VERIFY" "postgres.dump has no timescaledb extension"
log "postgres.dump: $(grep -c '^[0-9]' <<<"$toc") entries, TimescaleDB $(info "$src" timescaledb)"

for bucket in $(info "$src" buckets | tr ',' ' '); do
  [[ -d $src/s3/$bucket ]] || die "$EXIT_VERIFY" "bucket '$bucket' is listed but $src/s3/$bucket is missing"
done
log "objects: $(info "$src" objects)"
log "backup OK: $src"
