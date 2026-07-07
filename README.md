# navindex

Navigation indexes for large codebases — a compact `line → symbol` header at the top of big
source files, plus a `__navi__.md` outline map per folder. Read the top of a file (or one folder
map) and you know where every function lives, without opening the whole file or grepping blindly.

One dependency-free Python script does both jobs. Works in any git repo for Python, JS/JSX/TS/TSX,
and PowerShell. Ships as a [Claude Code](https://claude.com/claude-code) skill (`SKILL.md`), but the
script runs standalone too.

## What it produces

- **In-file header** — a comment block at the very top of a large file mapping each line number to
  the symbol there (functions, classes and their methods, TS interfaces/types/enums, route
  handlers, section banners). Read the first ~40 lines, jump straight to what you need.
- **Folder map (`__navi__.md`)** — per substantial folder: every code file → its symbol outline
  with exact line numbers, every doc file → a one-line descriptor, and a breadcrumb up to the root.
- **Root tree (`__navi__.md` at the repo root)** — every folder → the files it holds and a pointer
  to that folder's map. One read shows the whole layout.

Find a function deep in the tree: read the root tree (which folder) → read that folder map (which
line) → open the file. Two index reads, no blind grep.

## Requirements

Python 3 (standard library only — no `pip install`).

## Usage

Run from inside the target repo (the repo root is auto-detected from the nearest ancestor `.git`).

Refresh one or more files' headers (any size, idempotent):

```
python scripts/navindex.py path/to/file.py [more.ts ...]
```

Map a folder — rebuilds its `__navi__.md` and refreshes headers on large files in one pass:

```
python scripts/navindex.py backend/src --depth 4
```

Pass no argument to map the whole repo from its root.

Common flags (folder mode): `--depth N` recursion depth, `--threshold N` min lines for an in-file
header (default 300), `--min-lines` / `--max-lines` size gates, `--map-only` / `--no-map`. Full
table and semantics in [`SKILL.md`](SKILL.md).

Install the pre-commit hook once and headers keep themselves fresh at every commit:

```
python scripts/navindex.py --install-hook
```

The indexes are **generated from the code**, so regenerate maps after structural changes — a stale
index is worse than none. Both modes are idempotent (the header is stripped and rebuilt, not
stacked), re-running is safe, and rewrites preserve the file's original line endings (LF repos
stay LF on Windows).

## Housekeeping

Commit the `__navi__.md` maps and in-file headers — they are part of the source. Don't commit
`.navindex-cache.json` (a disposable local cache; already in `.gitignore`).

## Documentation

- [`SKILL.md`](SKILL.md) — full skill spec: when to read vs. regenerate, every flag, the skip list.
- [`references/internals.md`](references/internals.md) — exact symbol-extraction rules per language
  and how the cache hash is computed.

## License

[MIT](LICENSE)
