"""Read and validate a kb-intake contract v2 delivery package (design §3 import; kb-intake design v2 §5).

A package is `<doc_id>@<sha256(source.pdf)[:12]>/` holding manifest.json, source.pdf and the jsonl / json files
listed in manifest.files. kb-core accepts only confirmed packages of contract version "2" whose every file hash and
every row matches the schemas in contract/intake-v2/. kb-core never parses source.pdf; it only checks its hash.
"""

import hashlib
import json
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

from kb_core.paths import data_dir

CONTRACT = data_dir("contract") / "intake-v2"
CONTRACT_VERSION = "2"
NAME = re.compile(r"(?P<doc_id>[a-z0-9][a-z0-9._-]*)@(?P<sha>[0-9a-f]{12})")
SCHEMA_OF = {"pages.jsonl": "page", "regions.jsonl": "region", "tables.jsonl": "table", "layout.jsonl": "layout",
             "gaps.jsonl": "gap", "review.jsonl": "review", "llm.jsonl": "llm", "workflow.json": "workflow"}
REQUIRED = ("pages.jsonl", "regions.jsonl", "tables.jsonl", "layout.jsonl", "gaps.jsonl", "workflow.json")


class PackageError(ValueError):
    pass


@cache
def _validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((CONTRACT / f"{kind}.schema.json").read_text()))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rows(path: Path) -> Iterator[dict]:
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


class Package:
    def __init__(self, path: Path, manifest: dict):
        self.path = path
        self.manifest = manifest
        self.doc_id: str = manifest["doc_id"]
        self.sha256: str = manifest["source"]["sha256"]
        self.sha12: str = self.sha256[:12]
        self.declaration: dict = manifest["metadata"]["declaration"]
        self.source_pdf = path / "source.pdf"
        self._words: dict[int, list] | None = None

    @property
    def name(self) -> str:
        return self.path.name

    def pages(self) -> Iterator[dict]:
        return _rows(self.path / "pages.jsonl")

    def regions(self) -> Iterator[dict]:
        return _rows(self.path / "regions.jsonl")

    def tables(self) -> Iterator[dict]:
        return _rows(self.path / "tables.jsonl")

    def gaps(self) -> Iterator[dict]:
        return _rows(self.path / "gaps.jsonl")

    def words(self, page_no: int) -> list[list]:
        if self._words is None:
            self._words = {r["page_no"]: r["words"] for r in _rows(self.path / "layout.jsonl")}
        return self._words.get(page_no, [])


def validate(path: Path) -> Package:
    """Check a package folder against contract v2; return it, or raise PackageError naming the first problems."""
    path = Path(path)
    m = NAME.fullmatch(path.name)
    if not m:
        raise PackageError(f"folder name {path.name!r} is not <doc_id>@<sha256[:12]>")
    try:
        manifest = json.loads((path / "manifest.json").read_text())
    except (OSError, ValueError) as e:
        raise PackageError(f"{path.name}: cannot read manifest.json: {e}") from None
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise PackageError(f"{path.name}: contract_version is {manifest.get('contract_version')!r}, kb-core reads "
                           f"{CONTRACT_VERSION!r}")
    errors = [f"manifest.json: {e.message}" for e in _validator("manifest").iter_errors(manifest)][:5]
    if errors:
        raise PackageError(f"{path.name}: " + "; ".join(errors))
    if manifest["status"]["state"] != "confirmed":
        raise PackageError(f"{path.name}: status is {manifest['status']['state']!r}; only confirmed packages are read")
    if manifest["doc_id"] != m.group("doc_id") or manifest["package"] != path.name:
        raise PackageError(f"{path.name}: folder name does not match manifest doc_id / package")
    if not (path / "source.pdf").is_file() or _sha256(path / "source.pdf") != manifest["source"]["sha256"]:
        raise PackageError(f"{path.name}: source.pdf is missing or its sha256 differs from the manifest")
    if not manifest["source"]["sha256"].startswith(m.group("sha")):
        raise PackageError(f"{path.name}: folder name does not match the sha256 of source.pdf")
    listed = manifest["files"]
    for name in REQUIRED:
        if name not in listed:
            raise PackageError(f"{path.name}: {name} is not listed in manifest.files")
    for name, info in listed.items():
        f = path / name
        if not f.is_file():
            raise PackageError(f"{path.name}: {name} is listed but missing")
        if f.stat().st_size != info["bytes"] or _sha256(f) != info["sha256"]:
            raise PackageError(f"{path.name}: {name} does not match its sha256 / size in the manifest")
    for name, kind in SCHEMA_OF.items():
        if name not in listed:
            continue
        v = _validator(kind)
        rows = [json.loads((path / name).read_text())] if name.endswith(".json") else _rows(path / name)
        for i, row in enumerate(rows, 1):
            err = next(v.iter_errors(row), None)
            if err is not None:
                where = "/".join(str(p) for p in err.absolute_path)
                raise PackageError(f"{path.name}: {name} row {i} {where}: {err.message}")
    return Package(path, manifest)
