"""`kb-core import`: validate delivery packages, keep a read-only copy, register them in Postgres (design §3).

A path is either one package or a delivery folder holding packages. Importing the same package again is a no-op;
a different package for an already imported doc_id is refused (re-importing a changed document needs an explicit
decision, not a silent overwrite). Intake gaps are inherited into quality.gap_log with layer 'intake'.
Every document gets an access label (classification, owner, ...) from the overlay config/access_labels.yaml until
kb-intake carries labels (round 2 W3, CR-2); a document left without classification or owner is refused.
"""

import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from kb_core.access.labels import LabelError, doc_label, load_overlay
from kb_core.config import Settings
from kb_core.intake.package import NAME, Package, PackageError, validate
from kb_core.queries import pg_query


@dataclass(frozen=True)
class ImportResult:
    doc_id: str
    package: str
    created: bool


def package_dirs(path: Path) -> list[Path]:
    path = Path(path)
    if NAME.fullmatch(path.name):
        return [path]
    if not path.is_dir():
        raise PackageError(f"{path} is neither a package nor a delivery folder")
    found = sorted(p for p in path.iterdir() if p.is_dir() and NAME.fullmatch(p.name))
    if not found:
        raise PackageError(f"no <doc_id>@<sha12> packages in {path}")
    return found


WRITE = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


def _readonly_copy(src: Path, dest: Path) -> None:
    tmp = dest.with_name(f".tmp-{dest.name}-{uuid.uuid4().hex[:8]}")
    shutil.copytree(src, tmp)
    tmp.rename(dest)
    for p in sorted(dest.rglob("*"), reverse=True) + [dest]:   # files first, the package folder itself last
        p.chmod(p.stat().st_mode & ~WRITE)


def _remove(dest: Path) -> None:
    for p in [dest, *dest.rglob("*")]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)
    shutil.rmtree(dest)


def _q(name: str) -> str:
    return pg_query(name)[1]


def _register(conn: psycopg.Connection, pkg: Package, started: datetime, access: dict) -> None:
    d, meta = pkg.declaration, pkg.manifest["metadata"]
    period_end = date.fromisoformat(d["period_end"])
    conn.execute(_q("I02_insert_source"), {"issuer_id": d["issuer_id"], "publisher": d.get("publisher")})
    conn.execute(_q("I03_insert_document"), {
        "doc_id": pkg.doc_id, "issuer_id": d["issuer_id"], "doc_type": d["doc_type"], "period_end": period_end,
        "fiscal_year": period_end.year, "lang": d.get("lang") or meta.get("lang"), "source_url": d.get("source_url"),
        "completeness": Jsonb(d.get("completeness")), "translation_of": d.get("translation_of"),
        "publisher": d.get("publisher"), "published_at": d.get("published_at"), "page_count": meta["page_count"],
        "has_text_layer": meta.get("has_text_layer"), "package": pkg.name, "package_sha256": pkg.sha256,
        "contract_version": pkg.manifest["contract_version"], "manifest": Jsonb(pkg.manifest),
        "access": Jsonb(access)})
    with conn.cursor() as cur:
        cur.executemany(_q("I04_insert_intake_gap"), [{"doc_id": pkg.doc_id, "code": g["code"],
                                                       "page_no": g.get("page_no"), "detail": Jsonb(g)}
                                                      for g in pkg.gaps()])
    conn.execute(_q("B07_insert_ingest_run"), {
        "run_id": uuid.uuid4(), "doc_id": pkg.doc_id, "stage": "import", "status": "ok", "config_version": None,
        "started_at": started, "finished_at": datetime.now(UTC), "counts": Jsonb({"pages": meta["page_count"]}),
        "detail": Jsonb({"package": pkg.name}), "error": None})


def import_one(conn: psycopg.Connection, settings: Settings, path: Path, overlay: dict | None = None) -> ImportResult:
    started = datetime.now(UTC)
    pkg = validate(path)
    row = conn.execute(_q("I01_document_by_id"), {"doc_id": pkg.doc_id}).fetchone()
    if row is not None:
        if row[0] == pkg.sha256:
            return ImportResult(pkg.doc_id, row[1], False)
        raise PackageError(f"{pkg.doc_id} is already imported from {row[1]}; {pkg.name} has a different source.pdf")
    try:
        access = doc_label(overlay if overlay is not None else load_overlay(settings.access_labels), pkg.doc_id)
    except LabelError as e:
        raise PackageError(f"{pkg.doc_id}: access label: {e}") from None
    store = settings.store_dir / "packages"
    store.mkdir(parents=True, exist_ok=True)
    dest = store / pkg.name
    copied = False
    if dest.exists():
        # a copy left from an earlier import (e.g. after a database reset) must be the same delivery
        if (dest / "manifest.json").read_bytes() != (pkg.path / "manifest.json").read_bytes():
            raise PackageError(f"{pkg.name}: the store already holds a different delivery of this package ({dest}); "
                               "remove it from the store to import this one")
    else:
        _readonly_copy(pkg.path, dest)
        copied = True
    try:
        with conn.transaction():
            _register(conn, Package(dest, pkg.manifest), started, access)
    except Exception:
        if copied:
            _remove(dest)
        raise
    return ImportResult(pkg.doc_id, pkg.name, True)


def import_path(conn: psycopg.Connection, settings: Settings, path: Path) -> list[ImportResult]:
    """Import one package or every package of a delivery folder. Validation happens per package before anything
    is written for it; this function raises on the first invalid package (earlier ones stay imported). The CLI
    imports package by package instead and reports each failure."""
    return [import_one(conn, settings, p) for p in package_dirs(path)]
