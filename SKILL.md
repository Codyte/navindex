---
name: navindex
description: >-
  Generate and consult NAV INDEX navigation aids for a codebase: a compact line-range symbol
  header at the top of large source files, and a __navi__.md outline map per folder. Use this
  skill whenever you (1) finish substantially editing or creating a source file — refresh its
  header so its line numbers stay accurate; (2) add, remove, move, or rename files or symbols in
  a folder — regenerate that folder's __navi__.md; or (3) are about to explore or broadly search
  an unfamiliar area of a large codebase — read that folder's __navi__.md FIRST to orient in a
  single read instead of grepping blindly. Strongly prefer this skill when working in big files
  (1000+ lines), navigating an unfamiliar module, answering "where is X defined", building or
  refreshing code outlines / folder maps, or keeping navigation indexes current after a refactor.
  Works in any git repo for Python, JS/JSX/TS/TSX, and PowerShell.
---

# navindex — navigation indexes for large codebases

## Why this exists

Reading a 2000-line file or grepping blindly across an unfamiliar folder burns context and time.
NAV INDEX fixes that with three compact, always-accurate artifacts forming a **2-read navigation
model**: the root tree tells you *which folder*, the folder map tells you *which line*.

- **Root tree (`__navi__.md` at the repo root)** — a global index: every folder below → the files
  it holds (names + line counts, NO symbols) and a clickable pointer to that folder's own map. One
  read shows the whole repo layout and which folder map to open next. Written only on a repo-root
  run.
- **Folder map (`__navi__.md`, one per *substantial* folder)** — lists that folder's code files →
  their symbol outline (exact line numbers) and doc files → a one-line descriptor, plus a breadcrumb
  back up to the root tree. One read gives the detailed view of an entire area. Folders of trivial
  stubs (no extracted symbols and nothing past `--threshold`) get **no** map — they're listed in the
  root tree instead, and any stale map left behind by a prior run is auto-deleted. This keeps deep,
  narrow trees (e.g. one tiny `main.ps1` per leaf) from spawning hundreds of near-empty maps.
- **In-file header** — a comment block at the very top of a large source file mapping
  `line number → symbol` (functions, classes, decorators, route handlers, section banners). An
  agent that reads only the first ~40 lines instantly knows where everything is.

To find a function deep in the tree: read the **root tree** (locate its folder) → read that
**folder map** (locate its line) → open the file. Two index reads, no blind grep.

Both are **generated from the code**, so they never drift if you regenerate them after changes.
The whole point is accuracy: a stale index is worse than none, because it sends you to the wrong
line. That is why the discipline below ties regeneration to the moments code structure changes.

## When to READ an index (do this first)

- **To locate anything in an unfamiliar repo**, read the **root `__navi__.md` tree first** — it
  lists every folder and its files in one read, so you know exactly which folder map to open next.
- **Before a broad search or exploring an unfamiliar area**, read that folder's `__navi__.md` if
  one exists. It orients you in a single read — which file holds what, and at which lines — so you
  can open exactly the right file/lines instead of fanning out with grep.
- **When opening a large file**, read its NAV INDEX header (the top comment block) first and jump
  straight to the line you need.

If a `__navi__.md` looks out of date (line numbers don't match, files missing), regenerate it
(below) rather than trusting it.

## When to GENERATE / REFRESH

Regenerate right after the code structure changes, so the index stays trustworthy:

- **After substantially editing or creating a source file** → refresh that file's header so its
  line numbers are correct again. Small edits that don't move symbols don't need it; anything that
  shifts where functions live does.
- **After structural changes in a folder** (added / removed / moved files, renamed symbols, a big
  refactor) → regenerate that folder's `__navi__.md` (this also refreshes headers on large files
  in one pass).

By convention, a substantially edited or newly created source file should carry a NAV INDEX
header, and each large area should have a current `__navi__.md`.

**Or stop remembering: install the pre-commit hook once per repo** —
```
python <skill>/scripts/navindex.py --install-hook
```
Every commit then auto-refreshes headers on the staged source files (only files that already
carry a header or are at/above `--threshold`) and re-stages them, so committed headers can never
go stale. Delete `.git/hooks/pre-commit` to uninstall; a foreign pre-commit hook is never
overwritten. Folder maps still need a manual folder run after structural changes.

## How to run

One bundled script, `scripts/navindex.py`, does both jobs — it **auto-detects the mode from the
positional argument**: a file → refresh that file's header; a folder (or nothing) → build that
folder's `__navi__.md` and refresh headers inside it. **Run from the repository root** — the tool
detects the repo root from your current directory (nearest ancestor with a `.git`), and that's
where it writes its cache and computes paths. Invoke by the script's path inside this skill
(substitute the real skill path for `<skill>`):

**Refresh one (or more) file's header** — pass file paths (any size; idempotent):
```
python <skill>/scripts/navindex.py path/to/file.py [more.py ...]
```
Supported code: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.ps1`.

**Refresh a whole folder** — pass a directory; regenerates `__navi__.md` and refreshes headers on
large files in one pass:
```
python <skill>/scripts/navindex.py backend/src --depth 4
```
Pass no argument to map the whole repo from its root.

Flags (folder mode only; ignored in file mode):

| Flag | Default | Meaning |
|------|---------|---------|
| `paths` (positional) | repo root | a folder to map, OR file(s) to header-refresh |
| `--depth N` | 6 | how many subfolder levels to recurse (0 = root only). **Ignored on a repo-root run** — the global tree is always built full-depth so deep trees aren't silently truncated |
| `--threshold N` | 300 | minimum line count for a file to get an in-file header |
| `--min-lines N` | 0 | skip files shorter than N lines entirely (not even mapped) — drop trivial files |
| `--max-lines N` | 8000 | skip files longer than N lines (generated/huge) |
| `--map-only` | off | only (re)build `__navi__.md`, don't touch any headers |
| `--no-map` | off | only refresh headers, don't write `__navi__.md` |
| `--install-hook` | — | install a git pre-commit hook in the current repo (see above) |
| `--auto` | off | file mode: only touch files already carrying a header or at/above `--threshold` — what the hook passes |

The three line-count gates work together: a file is **considered** only when `--min-lines ≤ its
length ≤ --max-lines`; among considered code files, those at/above `--threshold` also get an
in-file header. (File mode — passing a path explicitly — always builds the header, ignoring these
gates, because you asked for that file by name.)

Folder mode is **cache-aware**: it stores a body-hash of each file in
`<repo_root>/.navindex-cache.json` and skips the header rewrite for unchanged files, so re-running
across a large tree is cheap. The output line `headers refreshed=R skipped=S` tells you what it did.

## Proof / sanity check

Both scripts are idempotent — re-running produces an identical file (the header is stripped and
rebuilt, not stacked). After generating, you can confirm the result is sound by re-running the
same command: a folder run should report `refreshed=0` for files you didn't change, and a
language compile/lint (e.g. `python -m compileall <dir>`) should still pass, since headers are
only comments.

## Housekeeping

- **Commit** the `__navi__.md` maps and the in-file headers — they're part of the source.
- **Don't commit** `.navindex-cache.json` — it's a disposable local cache. Add it to
  `.gitignore`.
- The driver never indexes: `node_modules`, `.git`, build/dist output, virtualenvs,
  `cache`/`.cache` and other caches, `migrations`/`alembic`, `vendor`, `volumes`, dotfolders,
  dotfiles, content-addressed cache blobs (sha-named files like `<hex>.json`), generated/minified
  bundles (`*.min.js`, `*.bundle.js`, `*.module.js`), `.env` files, or files over 8000 lines. If a
  symbol you expect is missing, see `references/internals.md` for the exact extraction rules.

For the precise symbol-extraction rules per language, the skip list rationale, and how the cache
hash is computed, read `references/internals.md`.
