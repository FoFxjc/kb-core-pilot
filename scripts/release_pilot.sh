#!/usr/bin/env bash
# Release a kb-core commit to the pilot repository as one history-free commit (docs/deploy.md, "Releasing a pilot").
#
#   scripts/release_pilot.sh <version> [commit]        (commit defaults to origin/main)
#
#   1. git archive the commit (export-ignore respected) into an empty folder; pyproject.toml must say <version>;
#      clone the pilot repository and stop if <version> is already released (exit 0 if this commit already is)
#   2. no .env, key or certificate files in the export, and scripts/check_clean.py on it: stop on any finding
#   3. pip wheel -c constraints.txt . from a copy of the export, then install the wheels into a fresh venv
#      (no index) and import kb_core
#   4. a generated note at the top of README.md (in the export only)
#   5. replace all of the pilot clone's files with the export, commit once:
#      "kb-core pilot <version> (snapshot of kb-core <sha>)"; kb-core's history never goes there
#   6. push, download the zip as a company machine would, and print the commit, the zip URL and its SHA-256
#
# The pilot repository is kb-core's origin with "-pilot" appended (https://github.com/<owner>/kb-core-pilot). The zip
# is downloaded and hashed only for a GitHub remote. PILOT_REMOTE overrides it (e.g. a local bare repository for a dry run); PYTHON names the Python 3.12 interpreter
# (default: python3.12 on PATH).
set -euo pipefail
export PIP_DISABLE_PIP_VERSION_CHECK=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGIN="$(git -C "$ROOT" remote get-url origin)"
PILOT_REMOTE="${PILOT_REMOTE:-${ORIGIN%.git}-pilot.git}"
PILOT_ZIP=""
case "$PILOT_REMOTE" in                                   # https or ssh form -> https://github.com/<owner>/<repo>
  *github.com[:/]*) REPO_PATH="${PILOT_REMOTE#*github.com?}"
                    PILOT_ZIP="https://github.com/${REPO_PATH%.git}/archive/refs/heads/main.zip" ;;
esac

die() { printf 'release_pilot: %s\n' "$*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

[ $# -ge 1 ] && [ $# -le 2 ] || die "usage: scripts/release_pilot.sh <version> [commit, default origin/main]"
VERSION="$1"
REF="${2:-origin/main}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version must look like 0.2.0, got '$VERSION'"
PY="$(command -v "${PYTHON:-python3.12}" || true)"
[ -n "$PY" ] && "$PY" -I -c 'import sys; assert sys.version_info[:2] == (3, 12)' \
  || die "no working Python 3.12 (set PYTHON to one)"

[ "$REF" = "origin/main" ] && git -C "$ROOT" fetch -q origin main
SHA="$(git -C "$ROOT" rev-parse --verify "$REF^{commit}")" || die "unknown commit '$REF'"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
EXPORT="$WORK/export"
mkdir "$EXPORT"

step "1/6 export kb-core $SHA"
git -C "$ROOT" archive --format=tar "$SHA" | tar -x -C "$EXPORT"
[ ! -e "$EXPORT/.git" ] && [ ! -e "$EXPORT/.env" ] || die "the export holds .git or .env"
grep -qx "version = \"$VERSION\"" "$EXPORT/pyproject.toml" \
  || die "pyproject.toml at $SHA is not version $VERSION: bump it in kb-core first"
printf '   %s files\n' "$(find "$EXPORT" -type f | wc -l | tr -d ' ')"
git clone -q "$PILOT_REMOTE" "$WORK/pilot"
LAST="$(git -C "$WORK/pilot" log -1 --format=%s 2>/dev/null || true)"
case "$LAST" in *"snapshot of kb-core $SHA)") echo "already released: $LAST"; exit 0 ;; esac
SUBJECTS="$(git -C "$WORK/pilot" log --format=%s 2>/dev/null || true)"
grep -qE "^kb-core pilot v?${VERSION//./\\.} " <<< "$SUBJECTS" \
  && die "version $VERSION is already in the pilot repository: bump the version"

step "2/6 secrets and check_clean on the export"
SECRETS="$(cd "$EXPORT" && find . \( -name '.env*' ! -name .env.example \) -o -name '*.pem' -o -name '*.key' \
  -o -name '*.p12' -o -name 'id_rsa*' -o -name 'id_ed25519*')"
[ -z "$SECRETS" ] || die "the export holds files that look like secrets: $SECRETS"
"$PY" -I "$EXPORT/scripts/check_clean.py" "$EXPORT" || die "check_clean found local or personal content"

step "3/6 wheels and an import smoke test"
cp -R "$EXPORT" "$WORK/build-src"                      # the build never writes into the export
"$PY" -m venv "$WORK/build"
"$WORK/build/bin/pip" wheel -q -w "$WORK/wheels" -c "$EXPORT/constraints.txt" "$WORK/build-src"
"$PY" -m venv "$WORK/smoke"
"$WORK/smoke/bin/pip" install -q --no-index --find-links "$WORK/wheels" -c "$EXPORT/constraints.txt" kb-core
(cd "$WORK" && "$WORK/smoke/bin/python" -I -c "
import importlib.metadata as m, kb_core
v = m.version('kb-core')
assert v == '$VERSION', v
print('   import kb_core ok, version', v)")
printf '   %s wheels\n' "$(ls "$WORK/wheels" | wc -l | tr -d ' ')"

step "4/6 generated note in README.md"
{ printf '> Generated from kb-core %s; do not open PRs here; install: docs/deploy.md\n\n' "$SHA"
  cat "$EXPORT/README.md"; } > "$WORK/README.md"
mv "$WORK/README.md" "$EXPORT/README.md"

step "5/6 commit to the pilot repository"
find "$WORK/pilot" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$EXPORT/." "$WORK/pilot/"
git -C "$WORK/pilot" add -A
git -C "$WORK/pilot" diff --cached --quiet && die "nothing changed since the last pilot release"
git -C "$WORK/pilot" commit -q -m "kb-core pilot $VERSION (snapshot of kb-core $SHA)"
COMMIT="$(git -C "$WORK/pilot" rev-parse HEAD)"
git -C "$WORK/pilot" cat-file -e "$SHA" 2>/dev/null && die "kb-core history reached the pilot repository"

step "6/6 push and download"
git -C "$WORK/pilot" push -q origin HEAD:main
printf '   pushed %s\n' "$COMMIT"
case "$PILOT_ZIP" in
  https://*)
    for _ in 1 2 3 4 5 6; do            # GitHub may fail or serve the previous archive for a few seconds after a push
      curl -fsSL -o "$WORK/pilot.zip" "$PILOT_ZIP" \
        && "$PY" -I -c "import sys, zipfile; sys.exit(zipfile.ZipFile(sys.argv[1]).comment.decode() != sys.argv[2])" \
             "$WORK/pilot.zip" "$COMMIT" && break
      rm -f "$WORK/pilot.zip"; sleep 10
    done
    [ -f "$WORK/pilot.zip" ] || die "pushed $COMMIT, but $PILOT_ZIP is not that commit yet: download it later and \
hash it (shasum -a 256 main.zip; the zip comment holds the commit: unzip -z main.zip)"
    ZIP_SHA="$("$PY" -I -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" \
      "$WORK/pilot.zip")"
    ;;
  *) PILOT_ZIP="(none: not a GitHub remote)"; ZIP_SHA="-" ;;
esac

printf '\nkb-core pilot %s\n  kb-core commit: %s\n  pilot commit:   %s\n  zip:            %s\n  zip SHA-256:    %s\n' \
  "$VERSION" "$SHA" "$COMMIT" "$PILOT_ZIP" "$ZIP_SHA"
