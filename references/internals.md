<!-- ====================== BEGIN NAV INDEX ====================== -->
<!-- NAV INDEX — auto-generated symbol map (refresh via the navindex skill) -->
<!--   L13    navindex internals -->
<!--   L18    What counts as a symbol (per language) -->
<!--   L84    Gitignored paths -->
<!--   L97    Where the header is inserted -->
<!--   L111   Pre-commit hook (`--install-hook`) -->
<!--   L121   Folder map (`__navi__.md`) format -->
<!--   L129   Skip rules -->
<!--   L142   Cache -->
<!-- ======================= END NAV INDEX ======================= -->

# navindex internals

Details for debugging "why didn't symbol X show up" or understanding the output. You don't need
this to use the skill — read it only when an index looks wrong.

## What counts as a symbol (per language)

Extraction is line-anchored (regex on the start of each line). Top-level declarations are
captured, plus **one nesting level: class members**, shown as `.name`. Member detection uses the
*member-indent rule*: the indent of the first non-blank line after a top-level `class` becomes
that class's member indent, and only lines at exactly that indent can be members — statements
inside method bodies sit deeper, so they can never false-positive. Any column-0 code line ends
the class body. Deeper nesting (closures, inner classes) is intentionally skipped.

**Python (`.py`)**
- `def`, `async def`, `class` at column 0 → the name
- `def` / `async def` at the member indent of a top-level class → `.name`
- A decorator line `@something(...)` at column 0 → the decorator text (so route handlers like
  `@router.get("/x")` show up)
- A module-level constant `NAME = ...` where NAME is `UPPER_SNAKE` (≥3 chars) → the name
- A banner comment line (`# ====`, `# ----`, 3+ dashes/equals) → its trimmed text

**JS / JSX / TS / TSX (`.js .jsx .ts .tsx`)**
- `export default function NAME`, `export function NAME`, `export async function NAME`
- `export const NAME`, top-level `function NAME`, top-level `const NAME = `
- `class NAME` / `export class NAME` / `export default class NAME` (also `abstract`) → `class NAME`
- `interface NAME`, `enum NAME`, `type NAME =` (with optional `export` / `declare`) → the name
- class methods at the member indent → `.name`: `name(args) {` single-line signatures (modifier
  prefixes `public/private/protected/static/readonly/async/get/set/override/abstract` allowed;
  keywords like `if`/`for`/`switch` excluded), and arrow-function fields `name = (…) =>`.
  A parameter list spanning multiple lines is missed — known ceiling.
- bare `export default ...` → labeled "export default"
- a `// ====` / `// ----` banner → its text

**Go (`.go`)**
- `type Name` declarations → `type Name`
- `func Name(...)` declarations → `Name`, including generic functions
- Methods → `Receiver.Name`; pointer and generic receiver syntax is normalized to the base type
- a `// ====` / `// ----` banner → its text

**C# (`.cs`)**
- `class` / `struct` / `interface` / `enum` / `record` with any modifier prefix → `class Name`,
  `interface IName`, … A **nested** type is indexed but does not reset the member indent, so the
  outer type's members declared after it are still found.
- Method, constructor or property at the member indent → `.Name`. The line must carry at least one
  modifier (`public`, `static`, `internal`, …) — that is what keeps statements out — and the
  return-type slot rejects `=`, so `static readonly Regex Rx = new Regex(...)` reads as a field,
  not as a method named `Regex`. Properties match `{ get` / `{ set` / `{ init` or an expression
  body (`=>`). Plain fields are not indexed.
- `case "literal":` → `case "literal"`, **at any nesting depth** — in a CLI the verb table is the
  jump target you actually search for. Numeric and enum cases are skipped (noise).
- a `// ====` / `// ----` banner → its trimmed text
- The member indent skips the lone `{` under the type declaration: in C# that brace sits at the
  *type's* indent, so taking it as the member indent would find no members at all.
- Ceiling: a signature spanning several lines is missed (single-line match only).

**PowerShell (`.ps1`)**
- `function Name` (case-insensitive) → the name
- `class Name` → `class Name` (members not indexed — rare; add if a repo needs it)
- a `param(` block → labeled "param()"
- a `# ====` / `# ----` banner → its text

**Markdown (`.md`)**
- ATX `#` and `##` headings outside fenced code blocks → the heading text
- Symbols live in a hidden HTML-comment NAV header inside the Markdown file
- The folder map does not repeat them; it only reports that header's exact line range
- `README.md`, `CONTRIBUTING.md`, `LICENSE`/`LICENSE.md`, and `SECURITY.md` never receive a header;
  a refresh removes one left by an older navindex version

Comment token is `//` for JS/TS, Go and C# files, `#` for everything else.

## Gitignored paths

In a git repo the walk skips anything `git ls-files --others --ignored --exclude-standard
--directory` reports (one subprocess per run; `core.quotePath=false`, or non-ASCII folder names
come back octal-escaped and never match). A wholly ignored folder is pruned at its top level, so
its children are never visited; an ignored file inside a tracked folder is dropped individually.
Tracked files are never affected — `--others` only lists untracked paths by construction.

This is a leak guard, not an optimization: the maps get committed, so a gitignored payload folder
would otherwise publish its folder and file names (customer projects, exports, scratch output) in
a public repo. `--include-ignored` restores the old behavior; no git, or not a repo, degrades to
mapping everything.

## Where the header is inserted

After any leading shebang (`#!...`) and module docstring / top block comment — so the docstring
stays first. For Go, build constraints and package documentation remain before `package`. For
Markdown, YAML front matter remains first and the header uses one HTML comment per line. The block
is delimited by `BEGIN NAV INDEX` / `END NAV INDEX` lines. On refresh, the
old block is stripped (plus one trailing blank line) and a fresh one inserted, which is what makes
it idempotent. Line numbers in the header account for the header's own height, so they point at
the real post-insertion lines.

**Line endings are preserved**: the rewrite detects the file's first line break (CRLF vs LF) and
writes the whole file back with that EOL, so a header refresh on Windows never CRLF-ifies an LF
repo (which would turn a 30-line header diff into a whole-file diff).

## Pre-commit hook (`--install-hook`)

`--install-hook` writes `.git/hooks/pre-commit` (marker: `# navindex pre-commit hook`). On each
commit it collects staged `.py/.js/.jsx/.ts/.tsx/.go/.ps1/.cs/.md` files, runs the script on them with
`--auto`, and re-stages them. `--auto` only touches files that already carry a header or are
at/above `--threshold` — small headerless files pass through untouched, and a run where every
file is skipped exits 0 so the commit proceeds. An existing pre-commit hook without the marker is
never overwritten (the installer aborts with instructions instead). Uninstall = delete the hook
file.

## Folder map (`__navi__.md`) format

- Grouped by subdirectory; code gets a `<sub>` preview of up to 24 `Lnnn:symbol` pairs.
- Markdown appears only as `**name** (N ln) — NAV Lstart-Lend`; its headings stay in that range.
- Other text/docs appear only by filename and line count, without descriptors or symbols.
- The map file lists both code (`.py .js .jsx .ts .tsx .go .ps1 .cs`) and docs (`.md .json .html .css
  .sql .yml .yaml .txt .toml .ini .cfg .sh`). `.env` is never listed.

## Skip rules

- **Directories never walked**: `__pycache__`, `node_modules`, `.git`, `dist`, `build`, `.venv`,
  `venv`, `.pytest_cache`, `.mypy_cache`, `migrations`, `alembic`, `assets`, `vendor`, `volumes`,
  and any dotfolder. Plus everything git ignores (see *Gitignored paths*), unless
  `--include-ignored`.
- **Files never indexed**: the generated `__navi__.md` itself; vendored/minified bundles
  (`*.min.js`, `*.bundle.js`, `*.module.js`, `three.js`, `chart.js`); anything longer than
  `--max-lines` (default 8000) or shorter than `--min-lines` (default 0, i.e. off).
- A file only gets an **in-file header** in folder mode if it's a code file at or above
  `--threshold` lines (default 300). Passing a file explicitly (file mode) adds a header
  regardless of size.

## Cache

`<repo_root>/.navindex-cache.json` maps `relative/path → {h, n, s}`: `h` = sha1 of the body with
any NAV INDEX block stripped, `n` = line count, `s` = the extracted symbol list. Because the hash
ignores the header block, it's stable across header refreshes: a file whose real content didn't
change hashes the same and is skipped (its symbols come from the cache, so the map rebuild doesn't
re-read it either). A `__ver__` field tracks the extraction-rule version — bumping `CACHE_VER` in
the script (done whenever symbol rules change) invalidates every cached symbol list at once.
Deleting the cache just forces a full refresh next run — it's purely an optimization, never
correctness-critical.
