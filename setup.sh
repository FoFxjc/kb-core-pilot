#!/usr/bin/env bash
# kb-core: install, migrate and check (design §9). Skeleton for round 1; hardened in the deployment round (step 6).
# Run it from anywhere; it works in the directory it lives in. Safe to run again.
#
#   1. read .env (KB_CORE_* only; variables already set in the environment win)
#   2. a Python 3.12 virtual environment in ./.venv (uv when available, else python3.12 -m venv)
#   3. pip install -c constraints.txt -e .   (from your pip index, e.g. the internal mirror; editable, so config/,
#      domains/ and eval/ in this folder are the ones kb-core reads)
#   4. kb-core migrate, then kb-core doctor
#
# Exit code 0 when kb-core is ready, 1 otherwise; every failure says why and what to do.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

step() { printf '\n== %s\n' "$*"; }
ok() { printf '   ok: %s\n' "$*"; }
fail() {  # fail "what went wrong" "what to do"
  printf '\nFAILED: %s\n' "$1" >&2
  [ -n "${2:-}" ] && printf 'What to do: %s\n' "$2" >&2
  exit 1
}

step "1/4 settings (.env)"
[ -f .env ] || fail "there is no .env in $ROOT" "copy .env.example to .env and fill it in"
while IFS= read -r line || [ -n "$line" ]; do
  line="${line#"${line%%[![:space:]]*}"}"
  case "$line" in ''|'#'*) continue ;; esac
  line="${line#export }"
  name="${line%%=*}"; value="${line#*=}"
  [ "$name" = "$line" ] && continue
  [[ "$name" =~ ^KB_CORE_[A-Z0-9_]*$ ]] || continue               # only KB_CORE_* names are read
  if [[ "$value" == \"*\"* || "$value" == \'*\'* ]]; then
    q="${value:0:1}"; value="${value:1}"; value="${value%%"$q"*}"
  else
    value="${value%% #*}"; value="${value%"${value##*[![:space:]]}"}"
  fi
  [ -n "${!name+x}" ] && continue                                 # the environment wins
  export "$name=$value"
done < .env
ok "settings read"

step "2/4 Python 3.12 environment (.venv)"
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null; then
    uv venv --python 3.12 .venv >/dev/null || fail "uv could not create .venv" "install Python 3.12 or check uv"
  else
    PY="$(command -v python3.12 || true)"
    [ -n "$PY" ] || fail "Python 3.12 not found" "install Python 3.12, or install uv"
    "$PY" -m venv .venv || fail "could not create .venv" "check your Python 3.12 installation"
  fi
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12)' || fail ".venv is not Python 3.12" "remove .venv and run again"
ok "$(.venv/bin/python --version)"

step "3/4 install (pip install -c constraints.txt -e .)"
if command -v uv >/dev/null; then
  uv pip install --python .venv/bin/python -q -c constraints.txt -e . || fail "install failed" "check PIP_INDEX_URL / network"
else
  .venv/bin/python -m pip install -q -c constraints.txt -e . || fail "install failed" "check PIP_INDEX_URL / network"
fi
ok "kb-core installed"

step "4/4 migrate and doctor"
.venv/bin/kb-core migrate || fail "migrate failed" "check KB_CORE_PG_DSN and that the database exists"
.venv/bin/kb-core doctor --report kb-core-doctor.json || fail "doctor found a problem" "read the FAIL lines above"
ok "kb-core is ready"
