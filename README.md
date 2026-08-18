# navindex

Navigation indexes for large codebases — a compact `line → symbol` header at the top of big
source and Markdown files, plus a `__navi__.md` outline map per folder. Read a file header (or folder
map) and you know where every function lives, without opening the whole file or grepping blindly.

One dependency-free Python script does both jobs. Works in any git repo for Python, JS/JSX/TS/TSX,
Go, PowerShell, C# and Markdown. Ships as a
[Claude Code](https://claude.com/claude-code) skill (`SKILL.md`); the script runs standalone too.

## What it produces

- **In-file header** — a comment block at the very top of a large file mapping each line number to
  the symbol there (functions, classes and their methods, TS interfaces/types/enums, route
  handlers, section banners). Read the first ~40 lines, jump straight to what you need.
- **Folder map (`__navi__.md`)** — code files show their symbol outline; Markdown shows only the
  line range of its own NAV header; other text files show only name/size. No duplicated doc outline.
- **Public-doc exceptions** — `README`, `CONTRIBUTING`, `LICENSE` and `SECURITY` stay header-free.
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

Map a folder — rebuilds its `__navi__.md`, refreshes large code headers and all Markdown headers:

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

## Benchmark

Measured on a large production codebase (real transcript token counts, not estimates). Locating and
describing 6 functions scattered through a **2528-line file**, using the in-file **NAV INDEX header**
instead of grepping cut the context the agent moved — at **identical 6/6 correctness**, on both the
cheapest and a frontier model:

| Model | Total context moved | Context re-sent per turn (cache-read) |
|---|---:|---:|
| Haiku | **−37 %** | **−46 %** |
| Opus | **−31 %** | **−49 %** |

Both arms navigated surgically (neither read the whole file), so these are conservative floors. The
**folder map** on a cross-file trace helps cheaper models more than frontier ones (model-dependent).
Across every run, **no `file:line` citation we spot-checked was fabricated** — the indexes give the
agent a factual anchor.

Full methodology, per-agent raw numbers, the exact reads each agent made, confounds, and everything
we did *not* measure: [`BENCHMARK.md`](BENCHMARK.md).

## Housekeeping

Commit the `__navi__.md` maps and in-file headers — they are part of the source. Don't commit
`.navindex-cache.json` (a disposable local cache; already in `.gitignore`).

## Documentation

- [`SKILL.md`](SKILL.md) — full skill spec: when to read vs. regenerate, every flag, the skip list.
- [`references/internals.md`](references/internals.md) — exact symbol-extraction rules per language
  and how the cache hash is computed.

## License

[MIT](LICENSE)
