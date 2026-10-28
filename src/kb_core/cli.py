"""kb-core command line: doctor, migrate, import, build, facts, reindex, serve, eval."""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

SUBCOMMANDS: dict[str, str] = {
    "doctor": "check the environment (ES, Postgres, folders, identity, model purposes)",
    "migrate": "apply Postgres migrations (safe to re-run)",
    "import": "validate and register delivery packages (a package or a delivery folder)",
    "build": "interpret imported documents into Postgres",
    "facts": "merge observations into facts across documents",
    "reindex": "rebuild the Elasticsearch indexes from Postgres",
    "serve": "HTTP API + MCP + UI",
    "eval": "run an evaluation",
}


def _out(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, default=str), flush=True)


def _settings():
    from kb_core.config import load_settings

    from kb_core.config import use

    s = load_settings()
    use(s)
    return s


def _migrate(args: argparse.Namespace) -> int:
    from kb_core.pg.db import connect
    from kb_core.pg.migrate import current_version, migrate

    with connect(_settings()) as conn:
        applied = migrate(conn)
        _out({"applied": applied, "version": current_version(conn)})
    return 0


def _doctor(args: argparse.Namespace) -> int:
    from pathlib import Path

    from kb_core.doctor import doctor_main

    return doctor_main(_settings(), Path(args.report) if args.report else None, args.check_endpoints)


def _import(args: argparse.Namespace) -> int:
    from dataclasses import asdict
    from pathlib import Path

    from kb_core.intake.importer import import_one, package_dirs
    from kb_core.intake.package import PackageError
    from kb_core.pg.db import connect

    s = _settings()
    target = Path(args.path).expanduser() if args.path else s.delivery_dir
    if target is None:
        print("kb-core import: give a package or delivery folder, or set KB_CORE_DELIVERY_DIR", file=sys.stderr)
        return 2
    failures = 0
    with connect(s) as conn:
        try:
            dirs = package_dirs(target)
        except PackageError as e:
            print(f"kb-core import: {e}", file=sys.stderr)
            return 1
        for d in dirs:
            try:
                _out(asdict(import_one(conn, s, d)))
            except PackageError as e:
                failures += 1
                _out({"package": d.name, "error": str(e)})
    return 1 if failures else 0


def _build(args: argparse.Namespace) -> int:
    from kb_core.build.run import build_doc
    from kb_core.pg.db import connect

    s = _settings()
    with connect(s) as conn:
        from kb_core.queries import pg_query

        ids = args.doc_ids or ([] if not args.all else
                               [r[0] for r in conn.execute(pg_query("I05_document_ids")[1])])
        if not ids:
            print("kb-core build: give doc_ids or --all", file=sys.stderr)
            return 2
        failures = 0
        for d in ids:
            try:
                run = build_doc(conn, s, d)
                _out({"doc_id": d, "run_id": run.run_id, "config_version": run.config_version[:12], **run.counts})
            except LookupError as e:
                failures += 1
                _out({"doc_id": d, "error": str(e)})
    return 1 if failures else 0


def _build_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("doc_ids", nargs="*")
    p.add_argument("--all", action="store_true", help="every imported document")


def _reindex(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from kb_core.es.client import es_client
    from kb_core.es.indexer import reindex
    from kb_core.pg.db import connect

    s = _settings()
    with connect(s) as conn:
        _out(asdict(reindex(conn, es_client(s), s, doc_id=args.doc)))
    return 0


def _serve(args: argparse.Namespace) -> int:
    from kb_core import doctor
    from kb_core.serve import app

    s = _settings()
    checks = doctor.run_checks(s)
    blocking = [c for c in checks if c.level == "fail" or (c.name == "es_indexes" and c.level != "ok")]
    if blocking:
        for c in blocking:
            print(f"kb-core serve: {c.name}: {c.detail}; {c.fix}", file=sys.stderr)
        print("kb-core serve: refusing to start (run kb-core doctor)", file=sys.stderr)
        return 1
    app.run(s)
    return 0


def _eval(args: argparse.Namespace) -> int:
    from kb_core.paths import data_dir
    from kb_core.pg.db import connect

    if args.kind == "compare":
        from kb_core.eval.compare import compare

        if len(args.sets) != 2:
            print("kb-core eval compare: give a baseline and a new recall result file", file=sys.stderr)
            return 2
        base, new = (json.loads(Path(f).read_text()) for f in args.sets)
        exceptions = None
        if args.exceptions:
            import yaml

            if args.pr is None:
                print("kb-core eval compare: --exceptions needs --pr (the PR the exceptions were approved for)",
                      file=sys.stderr)
                return 2
            exceptions = (yaml.safe_load(Path(args.exceptions).read_text()) or {}).get("exceptions") or []
        try:
            out = compare(base, new, exceptions=exceptions, pr=args.pr)
        except ValueError as e:
            print(f"kb-core eval compare: {e}", file=sys.stderr)
            return 2
        _out(out)
        return 1 if out["regressions"] else 0
    if args.kind == "snapshot":
        from kb_core.eval.snapshot import snapshot

        if len(args.sets) != 1:
            print("kb-core eval snapshot: give the output file", file=sys.stderr)
            return 2
        with connect(_settings()) as conn:
            snap = snapshot(conn)
        Path(args.sets[0]).write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
        _out(snap)
        return 0
    if args.kind == "headings":
        import yaml
        from psycopg.rows import dict_row

        from kb_core.eval.headings import match_headings
        from kb_core.queries import pg_query

        if not args.sets:
            print("kb-core eval headings: give judged heading sheets (eval/headings/*.judged.yaml)", file=sys.stderr)
            return 2
        docs = []
        with connect(_settings()) as conn, conn.cursor(row_factory=dict_row) as cur:
            for f in args.sets:
                sheet = yaml.safe_load(Path(f).read_text())
                nodes = cur.execute(pg_query("V1_tree_sample_nodes")[1], {"doc_id": sheet["doc_id"]}).fetchall()
                docs.append(match_headings(sheet, nodes))
        judged = sum(d["judged"] for d in docs)
        missed = sum(len(d["missed"]) for d in docs)
        totals = {"judged": judged, "found": sum(d["found"] for d in docs), "missed": missed,
                  "misplaced": sum(len(d["misplaced"]) for d in docs),
                  "missed_rate": round(missed / judged, 4) if judged else 0.0}
        _out({"totals": totals, "docs": docs})
        return 0
    if args.kind == "tree":
        import yaml

        from kb_core.eval.samples import record_tree_accuracy, tree_sheet

        if args.record:
            with connect(_settings()) as conn:
                _out([record_tree_accuracy(conn, yaml.safe_load(Path(f).read_text()), Path(f).name)
                      for f in args.record])
            return 0
        if not args.doc:
            print("kb-core eval tree: --doc is required", file=sys.stderr)
            return 2
        with connect(_settings()) as conn:
            sheet = tree_sheet(conn, args.doc, n=args.n, seed=args.seed)
        out = data_dir("eval") / "results" / f"tree_{args.doc}_{args.seed}.yaml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False, width=120))
        _out({"sheet": str(out), "sampled": sheet["sampled"]})
        return 0
    if args.kind == "concepts":
        import yaml

        from kb_core.eval.samples import concept_sheet

        with connect(_settings()) as conn:
            sheet = concept_sheet(conn, args.lang, n=args.n, seed=args.seed)
        out = data_dir("eval") / "results" / f"concepts_{args.lang}_{args.seed}.yaml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False, width=120))
        _out({"sheet": str(out), "sampled": sheet["sampled"]})
        return 0
    if args.kind == "recall":
        from kb_core.eval.recall import run

        if not args.sets:
            print("kb-core eval recall: name at least one question set (e.g. p1_questions)", file=sys.stderr)
            return 2
        _out(run(_settings(), args.sets, data_dir("eval") / "results", label=args.label, subject=args.subject))
        return 0
    print(f"kb-core eval {args.kind}: not implemented yet", file=sys.stderr)
    return 2


def _eval_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("kind", help="tree | concepts | headings | recall | compare | snapshot")
    p.add_argument("sets", nargs="*", help="recall: question sets under eval/ (e.g. p1_questions p1_crossyear p1_v3); "
                                           "compare: a baseline and a new result file (recall or snapshot); "
                                           "snapshot: the output file; headings: judged heading sheets")
    p.add_argument("--exceptions", metavar="FILE",
                   help="compare: YAML `exceptions:` list; an entry waives a lost node hit only with reason and "
                        "approved_by")
    p.add_argument("--pr", type=int, help="compare: the PR number this run is for (exceptions apply to it only)")
    p.add_argument("--label", help="recall: a label stored with the run")
    p.add_argument("--subject", default="full_access",
                   help="recall: the role the questions run as (default full_access: the regression gate)")
    p.add_argument("--record", nargs="+", metavar="SHEET",
                   help="tree: record judged sheets as each document's tree_sample_accuracy")
    p.add_argument("--doc")
    p.add_argument("--lang", default="en")
    p.add_argument("--seed", type=int, default=101)
    p.add_argument("--n", type=int, default=40)


def _facts(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from kb_core.build.run import run_facts
    from kb_core.pg.db import connect

    with connect(_settings()) as conn:
        _out(asdict(run_facts(conn)))
    return 0


# name -> handler(args) -> exit code; filled in as each command lands
HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {"migrate": _migrate, "doctor": _doctor,
                                                             "import": _import, "build": _build,
                                                             "reindex": _reindex, "serve": _serve,
                                                             "eval": _eval, "facts": _facts}
ARGS: dict[str, Callable[[argparse.ArgumentParser], None]] = {
    "doctor": lambda p: (p.add_argument("--report", help="also write a JSON report (no secrets) to this file"),
                         p.add_argument("--check-endpoints", action="store_true",
                                        help="also call each enabled model purpose's endpoint (GET /models)")),
    "build": _build_args,
    "eval": _eval_args,
    "reindex": lambda p: p.add_argument("--doc", help="reload one document only (full rebuild when no index exists)"),
    "import": lambda p: p.add_argument("path", nargs="?", help="a package or a delivery folder "
                                                                "(default: KB_CORE_DELIVERY_DIR)"),
}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kb-core", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in SUBCOMMANDS.items():
        p = sub.add_parser(name, help=help_)
        if name in ARGS:
            ARGS[name](p)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handler = HANDLERS.get(args.cmd)
    if handler is None:
        print(f"kb-core {args.cmd}: not implemented yet", file=sys.stderr)
        return 2
    from kb_core.config import ConfigError

    try:
        return handler(args)
    except ConfigError as e:
        print(f"kb-core {args.cmd}: configuration error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
