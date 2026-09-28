"""Measure surface-offset query latency on 10,000 wells (backend plan B1 exit criterion).

Creates a throwaway database next to the configured one, migrates it, loads 10,000 random
wells over ~130 x 140 km, runs 200 radius queries (1/5/10/20 km) and drops the database.

    cd backend && uv run python scripts/perf_offsets.py
"""

import os
import statistics
import subprocess
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

N_WELLS = 10_000
N_QUERIES = 200


def main() -> None:
    base = make_url(get_settings().database_url.get_secret_value())
    perf_url = base.set(database=f"{base.database}_perf")
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{perf_url.database}"'))
        c.execute(text(f'CREATE DATABASE "{perf_url.database}"'))
    try:
        env = {**os.environ, "SMRITI_DATABASE_URL": perf_url.render_as_string(hide_password=False)}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
        os.environ["SMRITI_DATABASE_URL"] = env["SMRITI_DATABASE_URL"]
        get_settings.cache_clear()
        from app.db.session import session_scope
        from app.geo.service import surface_offsets

        with session_scope() as s:
            s.execute(
                text(
                    "INSERT INTO field (name, basin, crs_epsg, synthetic) VALUES ('perf', 'perf', 32646, true)"
                )
            )
            s.execute(
                text(
                    "INSERT INTO well (canonical_name, aliases, field_id, status, lat, lon, datum_assumed, synthetic) "
                    "SELECT 'PERF-' || g, '{}', (SELECT id FROM field), 'completed', "
                    "27.0 + random() * 1.2, 94.8 + random() * 1.4, false, true "
                    f"FROM generate_series(1, {N_WELLS}) g"
                )
            )
            s.execute(
                text(
                    "UPDATE well SET surface_loc = ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography"
                )
            )
        with session_scope() as s:
            s.execute(text("ANALYZE well"))
            ids = [
                r[0]
                for r in s.execute(text(f"SELECT id FROM well ORDER BY random() LIMIT {N_QUERIES}"))
            ]
            times, counts = [], []
            for i, wid in enumerate(ids):
                t = time.perf_counter()
                counts.append(len(surface_offsets(s, wid, [1, 5, 10, 20][i % 4] * 1000)))
                times.append((time.perf_counter() - t) * 1000)
        times.sort()
        print(
            f"{N_WELLS} wells, {N_QUERIES} queries: p50 {statistics.median(times):.1f} ms, "
            f"p95 {times[int(0.95 * len(times)) - 1]:.1f} ms, max {times[-1]:.1f} ms, "
            f"mean offsets returned {statistics.mean(counts):.0f}"
        )
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{perf_url.database}" WITH (FORCE)'))


if __name__ == "__main__":
    main()
