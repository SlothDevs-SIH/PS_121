# Backups for the local / single-host stack

Three scripts, all run from any directory against the running compose stack:

| Script | What it does | Changes anything? |
|---|---|---|
| `backup.sh [--dir DIR] [--keep N]` | `pg_dump` of the database + a copy of every S3 bucket into `DIR/smriti-<UTC timestamp>/`, with a `SHA256SUMS` manifest; then deletes all but the newest `N` backups | only `DIR` |
| `verify.sh BACKUP_DIR` | checks the manifest, reads the dump's table of contents (`pg_restore --list`, no database connection) and the bucket folders | no |
| `restore.sh [--db NAME] [--no-db] [--no-s3] --yes BACKUP_DIR` | drops and re-creates the database from the dump, makes each backed-up bucket identical to the backup | **yes — destructive** |

`DIR` defaults to `$SMRITI_BACKUP_DIR` or `<repo>/backups` (the scripts write a `.gitignore` there
so dumps never reach git); `N` to `$SMRITI_BACKUP_KEEP` or 7. They need `docker` (with the compose
plugin) and bash; on Windows run them from Git Bash.

Exit codes are the same in every script: `0` ok, `2` usage (and `restore.sh` without `--yes`),
`3` precondition (a service not running, a backup already in progress, TimescaleDB version
mismatch), `4` database, `5` object store, `6` verification failed. A failed backup leaves
nothing behind (it is built in a `.partial` directory and only renamed when complete).

## What is backed up

| Data | How | Notes |
|---|---|---|
| PostgreSQL + TimescaleDB + PostGIS + pgvector (`postgres` service) | `pg_dump --format=custom` of the whole database via `docker compose exec -T postgres` | TimescaleDB's documented logical-backup procedure. pg_dump reads one consistent snapshot while the app keeps running. Warnings about circular foreign keys between hypertables and chunks are expected. |
| Object store buckets (`s3` service, SeaweedFS) | a one-off `rclone` container (image pinned by digest) on the stack's network, `rclone copy` of each bucket through the S3 API | raw documents and page images. They are write-once, and the database is dumped first, so every object the dump refers to is in the copy. |
| Redis | not backed up | Celery queue and caches only; lost tasks are re-queued by re-running ingestion. |
| Keycloak (`oidc` profile) | not backed up | dev mode, re-imported from `infra/keycloak/smriti-realm.json` at start. A production IdP is backed up by its owners. |
| Prometheus / Grafana data | not backed up | metrics history (7 days) and a provisioned dashboard. |

Each backup directory holds `postgres.dump`, `s3/<bucket>/...`, `backup-info.txt` (time, git
commit, server and extension versions, image references, buckets and object counts) and
`SHA256SUMS` over all of them.

## RPO and RTO

These are **targets for a nightly schedule on one host**, not measurements. Time your own
backups and restore drill against your data and write the numbers down.

- **RPO (data you can lose): 24 hours** with one backup a night. Run `backup.sh` more often to
  shorten it; each run is a full copy. Point-in-time recovery (WAL archiving) is not set up here.
  It belongs to the production database (the master plan's "pg_dump + WAL archiving").
- **RTO (time to be back): about 30 minutes** for the synthetic corpus: a few minutes of
  `pg_restore` plus the bucket copy, then the app restarts. It grows with the page-image volume
  (the S3 copy dominates) and the size of the `rt_sample` hypertable.
- Keep copies off the host. `--keep 7` on the same disk protects against mistakes, not against
  losing the machine: copy the newest `smriti-*` directory to other storage after each run.

## Schedule

Linux host (cron, 02:30 every night, keep 14, log to syslog):

```cron
30 2 * * * cd /opt/smriti && infra/backup/backup.sh --keep 14 2>&1 | logger -t smriti-backup
```

Add a weekly check (`verify.sh "$(ls -d /opt/smriti/backups/smriti-* | tail -n 1)"`) and alert on
a non-zero exit code of either job. On Windows use Task Scheduler with
`"C:\Program Files\Git\bin\bash.exe" -lc "cd /c/PS121 && infra/backup/backup.sh --keep 14"`.

## Verifying a backup

1. **Every backup:** `infra/backup/verify.sh backups/smriti-<timestamp>` checks the checksums, that
   `pg_restore` can read the dump and that it holds `alembic_version`, `well` and the `rt_sample`
   hypertable, and that every bucket folder is present. `backup.sh` already checks the manifest
   before it keeps a backup.
2. **Monthly: a restore drill.** Restore into a scratch database, which leaves the live one and
   the buckets alone:

   ```bash
   infra/backup/restore.sh --db smriti_drill --no-s3 backups/smriti-<timestamp>        # dry run: prints the plan
   infra/backup/restore.sh --db smriti_drill --no-s3 --yes backups/smriti-<timestamp>
   docker compose exec -T postgres psql -U smriti -d smriti_drill \
     -c "SELECT count(*) FROM well" -c "SELECT version_num FROM alembic_version"
   docker compose exec -T postgres psql -U smriti -d postgres -c "DROP DATABASE smriti_drill"
   ```

   Compare the counts with the live database and record the time taken (your RTO).

## Restoring

```bash
infra/backup/restore.sh backups/smriti-<timestamp>          # prints what it will overwrite, then refuses
infra/backup/restore.sh --yes backups/smriti-<timestamp>
```

`restore.sh` checks the manifest first and refuses a backup made with a different TimescaleDB
version (run the `postgres_image` from `backup-info.txt` instead). It stops the app containers
that hold database connections (`api`, `worker`, `stream`, `api-jwt`, `api-oidc`). It then
follows TimescaleDB's restore procedure: it drops and re-creates the database, runs
`CREATE EXTENSION timescaledb`, then `timescaledb_pre_restore()`, then a single-job
`pg_restore`, then `timescaledb_post_restore()`, the last one even when `pg_restore` failed.
Next it syncs each bucket from the backup, with objects not in the backup deleted, and starts
the containers again. If it fails part-way, it prints the `docker start` command for the
stopped containers. Check the result with `curl -sf http://127.0.0.1:8000/readyz`.
