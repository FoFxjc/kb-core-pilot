"""Postgres connections."""

import psycopg

from kb_core.config import Settings


def connect(settings: Settings, autocommit: bool = True) -> psycopg.Connection:
    return psycopg.connect(settings.pg_dsn, autocommit=autocommit, application_name="kb-core")
