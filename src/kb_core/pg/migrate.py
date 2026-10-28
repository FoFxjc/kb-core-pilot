"""Numbered SQL migrations (design §4.1): migrations/NNNN_name.sql, recorded in public.schema_migrations.

Each file runs once. All pending files run in one transaction under an advisory lock (each file in a savepoint),
so a failing file leaves the database at the version it started from. Re-running is a no-op. An applied file whose
content changed is refused: migrations are append-only, so a change needs a new file.
"""

import hashlib
import re
from pathlib import Path

import psycopg

from kb_core.paths import data_dir

MIGRATIONS = data_dir("migrations")
NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")
LOCK_KEY = 4242


class MigrationError(RuntimeError):
    pass


def _files(directory: Path) -> list[tuple[int, Path]]:
    out = []
    for p in sorted(directory.glob("*.sql")):
        m = NAME.fullmatch(p.name)
        if not m:
            raise MigrationError(f"migration file name {p.name!r} is not NNNN_name.sql")
        out.append((int(m.group(1)), p))
    versions = [v for v, _ in out]
    if versions != list(range(1, len(out) + 1)):
        raise MigrationError(f"migration numbers must be 1..{len(out)} without gaps, got {versions}")
    return out


def _ensure_table(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS public.schema_migrations (
        version    INT PRIMARY KEY,
        name       TEXT NOT NULL,
        sha256     TEXT NOT NULL,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def current_version(conn: psycopg.Connection) -> int:
    exists = conn.execute("SELECT to_regclass('public.schema_migrations')").fetchone()[0]
    if exists is None:
        return 0
    return conn.execute("SELECT coalesce(max(version), 0) FROM public.schema_migrations").fetchone()[0]


def latest_version(directory: Path = MIGRATIONS) -> int:
    return len(_files(directory))


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS) -> list[str]:
    """Apply pending migrations; return the names applied (empty when up to date)."""
    files = _files(directory)
    applied: list[str] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_KEY])
        _ensure_table(conn)
        done = {v: (n, s) for v, n, s in conn.execute("SELECT version, name, sha256 FROM public.schema_migrations")}
        for version, path in files:
            sql = path.read_text()
            sha = hashlib.sha256(sql.encode()).hexdigest()
            if version in done:
                name, recorded = done[version]
                if name != path.name or recorded != sha:
                    raise MigrationError(f"{path.name} was changed after it was applied (recorded {name} "
                                         f"sha256 {recorded[:12]}); add a new migration instead")
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO public.schema_migrations (version, name, sha256) VALUES (%s, %s, %s)",
                             [version, path.name, sha])
            applied.append(path.name)
    return applied
