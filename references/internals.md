# navindex internals

Details for debugging "why didn't symbol X show up" or understanding the output. You don't need
this to use the skill — read it only when an index looks wrong.

## What counts as a symbol (per language)

Extraction is line-anchored (regex on the start of each line), so only **top-level** declarations
are captured — nested/indented definitions are intentionally skipped to keep the outline flat and
useful.

**Python (`.py`)**
- `def`, `async def`, `class` at column 0 → the name
- A decorator line `@something(...)` at column 0 → the decorator text (so route handlers like
  `@router.get("/x")` show up)
- A module-level constant `NAME = ...` where NAME is `UPPER_SNAKE` (≥3 chars) → the name
- A banner comment line (`# ====`, `# ----`, 3+ dashes/equals) → its trimmed text

**JS / JSX / TS / TSX (`.js .jsx .ts .tsx`)**
- `export default function NAME`, `export function NAME`, `export async function NAME`
- `export const NAME`, top-level `function NAME`, top-level `const NAME = `
- bare `export default ...` → labeled "export default"
- a `// ====` / `// ----` banner → its text

**PowerShell (`.ps1`)**
- `function Name` (case-insensitive) → the name
- a `param(` block → labeled "param()"
- a `# ====` / `# ----` banner → its text

Comment token is `//` for JS/TS files, `#` for everything else.

## Where the header is inserted

After any leading shebang (`#!...`) and module docstring / top block comment — so the docstring
stays first. The block is delimited by `BEGIN NAV INDEX` / `END NAV INDEX` lines. On refresh, the
old block is stripped (plus one trailing blank line) and a fresh one inserted, which is what makes
it idempotent. Line numbers in the header account for the header's own height, so they point at
the real post-insertion lines.

## Folder map (`__navi__.md`) format

- Grouped by subdirectory; each file shown as `**name** (N ln) — head`, where `head` is a doc
  descriptor (for docs) or the first few symbols (for code).
- Code files also get a `<sub>` line previewing up to 24 `Lnnn:symbol` pairs.
- Doc descriptors: Markdown → first heading; JSON → `name`/`title`/`id`/`description` or top keys.
- The map file lists both code (`.py .js .jsx .ts .tsx .ps1`) and docs (`.md .json .html .css
  .sql .yml .yaml .txt .toml .ini .cfg .sh`). `.env` is never listed.

## Skip rules

- **Directories never walked**: `__pycache__`, `node_modules`, `.git`, `dist`, `build`, `.venv`,
  `venv`, `.pytest_cache`, `.mypy_cache`, `migrations`, `alembic`, `assets`, `vendor`, `volumes`,
  and any dotfolder.
- **Files never indexed**: the generated `__navi__.md` itself; vendored/minified bundles
  (`*.min.js`, `*.bundle.js`, `*.module.js`, `three.js`, `chart.js`); anything longer than
  `--max-lines` (default 8000) or shorter than `--min-lines` (default 0, i.e. off).
- A file only gets an **in-file header** in folder mode if it's a code file at or above
  `--threshold` lines (default 300). Passing a file explicitly (file mode) adds a header
  regardless of size.

## Cache

`<repo_root>/.navindex-cache.json` maps `relative/path → sha1(body with NAV INDEX stripped)`.
Because the hash ignores the header block, it's stable across header refreshes: a file whose real
content didn't change hashes the same and is skipped. Deleting the cache just forces a full
refresh next run — it's purely an optimization, never correctness-critical.
