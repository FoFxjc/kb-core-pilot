import json

import pytest

from kb_core.intake.package import Package, PackageError, validate
from tests.fixtures.mini_package import DOC, build_package


def test_validate_accepts_fixture(tmp_path):
    pkg = validate(build_package(tmp_path))
    assert isinstance(pkg, Package)
    assert pkg.doc_id == DOC and len(pkg.sha12) == 12
    assert pkg.declaration["issuer_id"] == "acme"
    assert [p["page_no"] for p in pkg.pages()] == [1, 2, 3]
    assert len(list(pkg.regions())) == 8 and len(list(pkg.tables())) == 2
    assert pkg.words(2)[0][4] == "Overview"
    assert [g["code"] for g in pkg.gaps()] == ["low_confidence"]
    assert pkg.source_pdf.name == "source.pdf"


def test_rejects_wrong_contract_version(tmp_path):
    with pytest.raises(PackageError, match="contract_version"):
        validate(build_package(tmp_path, contract_version="3"))


def test_rejects_unconfirmed(tmp_path):
    with pytest.raises(PackageError, match="confirmed"):
        validate(build_package(tmp_path, state="in_review"))


def test_rejects_tampered_file_hash(tmp_path):
    def tamper(pkg):
        with (pkg / "regions.jsonl").open("a") as f:
            f.write("\n")
    with pytest.raises(PackageError, match="regions.jsonl"):
        validate(build_package(tmp_path, after=tamper))


def test_rejects_schema_violation(tmp_path):
    def bad_region(files):
        files["regions.jsonl"][0]["type"] = "banner"
    with pytest.raises(PackageError, match="regions.jsonl"):
        validate(build_package(tmp_path, mutate=bad_region))


def test_rejects_folder_name_that_does_not_match_source(tmp_path):
    pkg = build_package(tmp_path)
    renamed = pkg.with_name(f"{DOC}@000000000000")
    pkg.rename(renamed)
    with pytest.raises(PackageError, match="folder name"):
        validate(renamed)


def test_rejects_missing_file(tmp_path):
    pkg = build_package(tmp_path)
    (pkg / "tables.jsonl").unlink()
    with pytest.raises(PackageError, match="tables.jsonl"):
        validate(pkg)


def test_font_colour_not_in_v2_schema_yet(tmp_path):
    """CR-1 is not in contract v2 yet: font.color fails v2 validation until the contract adds it."""
    def colour(files):
        files["regions.jsonl"][0]["font"]["color"] = "#df271c"
    with pytest.raises(PackageError):
        validate(build_package(tmp_path, mutate=colour))


def test_manifest_round_trip(tmp_path):
    pkg = validate(build_package(tmp_path))
    assert pkg.manifest == json.loads((pkg.path / "manifest.json").read_text())
