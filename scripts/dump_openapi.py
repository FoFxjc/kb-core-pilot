"""Write the HTTP API's OpenAPI document to web/openapi.json (input of web/scripts/gen-api.mjs)."""

import json
import sys
from pathlib import Path

from kb_core.config import load_settings
from kb_core.serve.app import create_app

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    app = create_app(load_settings({"KB_CORE_PG_DSN": "postgresql://unused", "KB_CORE_ES_URL": "http://unused"},
                                   env_file=None))
    out = ROOT / "web" / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")
    print(out.relative_to(ROOT), file=sys.stderr)
