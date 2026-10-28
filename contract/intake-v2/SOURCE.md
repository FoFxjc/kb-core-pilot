# Source of this contract copy

- Repository: the kb-intake repository
- Path: `contract/v2/*.schema.json` (9 files; copies identical to upstream except the top-level `$id`, which is
  a neutral `urn:kb-intake:contract:v2:<name>` here)
- Source commit: fc9b4b434a5a807f8e191a9d9817b51d3bdf8261 (release 0.3.1)
- Copied: 2026-10-26

`contract/intake-v2/` is the only schema kb-core validates packages against. Check that it still matches upstream with
`KB_CORE_INTAKE_REPO=/path/to/kb-intake uv run python scripts/check_contract.py`. Contract v2 only gains fields; kb-core never edits these files. Requests for
contract changes go to `docs/contract-requests.md`.
