// Generates src/api/schema.gen.ts from openapi.json (written by `uv run python scripts/dump_openapi.py`).
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, '../openapi.json');
const target = resolve(here, '../src/api/schema.gen.ts');

const { default: openapiTS, astToString } = await import('openapi-typescript');
const doc = JSON.parse(await readFile(source, 'utf8'));
const ast = await openapiTS(doc, { silent: true, alphabetize: true });
const header = '// Generated from web/openapi.json by scripts/gen-api.mjs (openapi-typescript). Do not edit.\n\n';
await writeFile(target, header + astToString(ast));
console.log('gen-api: src/api/schema.gen.ts');
