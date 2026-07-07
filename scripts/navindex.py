"""navindex — one universal NAV INDEX tool (per-file headers + folder maps).

Two modes, auto-detected from the positional argument:
  • FILE mode   — pass one or more files → refresh each file's NAV INDEX header (any size).
  • FOLDER mode — pass a single folder (or nothing → repo root) → (re)build that folder's
                  __navi__.md map AND refresh headers on large files in one pass.

Portable: the repo root is detected from the current working directory (nearest ancestor with a
.git, else CWD) — NOT from where this script lives — so the bundled skill works in any repo. Run
it from inside the target repo.

Idempotent: re-running rebuilds the header/map in place (the old block is stripped first), so it
never stacks. Supported code: .py, .js/.jsx/.ts/.tsx, .ps1.

Usage:
  python navindex.py path/to/file.py [more.py ...]        # FILE mode
  python navindex.py backend/src --depth 4                # FOLDER mode
  python navindex.py                                       # FOLDER mode on the repo root
  python navindex.py --install-hook                        # pre-commit hook: headers never stale
Folder flags: --depth N (recursion, default 6) · --threshold N (min lines for a header,
default 300) · --min-lines N (skip files shorter than N entirely, default 0) · --max-lines N
(skip files longer than N — generated/huge, default 8000) · --map-only (only __navi__.md) ·
--no-map (only headers). File flags: --auto (only files already carrying a header or at/above
--threshold — what the pre-commit hook passes).
"""
# ====================== BEGIN NAV INDEX ======================
# NAV INDEX — auto-generated symbol map (refresh via the navindex skill)
#   L67    TOP
#   L69    per-file core
#   L71    comment_token
#   L74    file_eol
#   L86    JS_KW
#   L89    symbols
#   L153   docstring_end
#   L173   strip_old
#   L183   build
#   L215   folder driver
#   L217   CODE_EXT
#   L218   SKIP_DIRS
#   L222   CACHE_VER
#   L223   HASHFILE
#   L224   MAX_LINES
#   L225   DOC_EXT
#   L227   MAP_NAME
#   L228   CACHE_NAME
#   L230   _is_vendor
#   L234   find_repo_root
#   L247   doc_descriptor
#   L269   body_hash
#   L280   walk
#   L297   run_folder
#   L401   _is_generated_map
#   L411   cleanup_stale_maps
#   L428   _is_detailed
#   L435   write_map
#   L468   write_tree
#   L493   pre-commit hook
#   L495   HOOK_MARK
#   L497   _wants_header
#   L508   install_hook
#   L543   entrypoint
#   L545   main
# ======================= END NAV INDEX =======================

import argparse, hashlib, json, os, re, sys, datetime

TOP = "NAV INDEX — auto-generated symbol map (refresh via the navindex skill)"

# ---------------------------------------------------------------- per-file core

def comment_token(path):
    return "//" if os.path.splitext(path)[1] in (".js", ".jsx", ".ts", ".tsx") else "#"

def file_eol(path):
    """'\\r\\n' if the file's first line break is CRLF, else '\\n'. Rewrites must keep the
    original EOL: open(..., 'w') without newline= translates \\n -> os.linesep, which would
    CRLF-ify an LF repo on Windows and turn a header refresh into a whole-file diff."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
    except OSError:
        return "\n"
    j = chunk.find(b"\n")
    return "\r\n" if j > 0 and chunk[j - 1:j] == b"\r" else "\n"

JS_KW = {"if", "for", "while", "switch", "catch", "return", "else", "do", "try",
         "new", "function", "typeof", "await", "yield"}  # never method names

def symbols(lines, ext):
    out = []
    in_class = False   # inside a top-level class body → members index as ".name"
    m_indent = None    # member indent = indent of the FIRST non-blank line after `class`;
                       # only lines at exactly that indent are members, so statements inside
                       # method bodies (always deeper) can never false-positive as methods.
    for i, ln in enumerate(lines, 1):
        s = ln.rstrip("\n")
        ind = len(s) - len(s.lstrip())
        if in_class and s.strip() and m_indent is None:
            m_indent = ind
        if ext in (".js", ".jsx", ".ts", ".tsx"):
            m = (re.match(r"^export default (?:abstract )?class (\w+)", s)
                 or re.match(r"^(?:export )?(?:abstract )?class (\w+)", s))
            if m:
                out.append((i, "class " + m.group(1))); in_class, m_indent = True, None; continue
            if s and not s[0].isspace() and not s.startswith("//"):
                in_class, m_indent = False, None  # any other column-0 code ends the class body
            m = (re.match(r"^export default function (\w+)", s) or re.match(r"^export (?:async )?function (\w+)", s)
                 or re.match(r"^export const (\w+)", s) or re.match(r"^(?:async )?function (\w+)", s)
                 or re.match(r"^const (\w+) = ", s)
                 or re.match(r"^(?:export )?(?:declare )?(?:interface|enum) (\w+)", s)
                 or re.match(r"^(?:export )?type (\w+) *=", s))
            if m: out.append((i, m.group(1)))
            elif re.match(r"^export default ", s): out.append((i, "export default"))
            elif in_class and ind == m_indent and (
                    (mm := re.match(r"^\s+(?:(?:public|private|protected|static|readonly|async|get|set|override|abstract)\s+)*(\w+)\s*\([^)]*\)[^;{}]*\{[\s}]*$", s))
                    or (mm := re.match(r"^\s+(?:(?:public|private|protected|static|readonly)\s+)*(\w+)\s*=\s*(?:async\s*)?\(", s))):
                # ponytail: single-line signatures only — a param list spanning lines is missed
                if mm.group(1) not in JS_KW: out.append((i, "." + mm.group(1)))
            elif re.match(r"^// ?[-=]{3,}", s):
                lbl = s.lstrip("/ -=")[:70]
                if lbl: out.append((i, lbl))  # drop banners that are only dashes/equals (empty label)
        elif ext == ".ps1":
            m = re.match(r"^\s*function\s+([\w-]+)", s, re.I)
            if m: out.append((i, m.group(1)))
            # NOTE: bare `param(` blocks are intentionally NOT indexed — they're not jump targets
            # (the function name above them is), and every function has one, so they flood the map.
            elif re.match(r"^class\s+([\w-]+)", s, re.I):
                # ponytail: PS class methods not indexed — rare; add member matching if a repo needs it
                out.append((i, "class " + re.match(r"^class\s+([\w-]+)", s, re.I).group(1)))
            elif re.match(r"^#\s?[-=]{3,}", s):
                lbl = s.lstrip("# -=")[:70]
                if lbl: out.append((i, lbl))
        else:
            m = re.match(r"^(async def|def|class) (\w+)", s)
            if m:
                out.append((i, m.group(2)))
                in_class, m_indent = (m.group(1) == "class"), None
                continue
            if s and s[0] not in " \t#@":
                in_class, m_indent = False, None  # column-0 code (not comment/decorator) ends the class
            if in_class and ind == m_indent and (mm := re.match(r"^\s+(?:async def|def) (\w+)", s)):
                out.append((i, "." + mm.group(1)))
            # Route decorators only (they carry the URL path) — skip @lru_cache/@property/@validator
            # etc., whose real symbol is the def on the next line anyway.
            elif re.match(r"^@\w[\w.]*\.(?:get|post|put|patch|delete|head|options|websocket|route)\(", s):
                out.append((i, s.strip()[:70]))
            elif re.match(r"^# ?[-=]{3,}", s):
                lbl = s.lstrip("# -=")[:70]
                if lbl: out.append((i, lbl))  # drop banners that strip to empty
            elif re.match(r"^[A-Z_][A-Z0-9_]{2,} = ", s): out.append((i, s.split("=")[0].strip()))
    return out

def docstring_end(lines, ext):
    """Index (0-based) right after a leading module docstring / banner comment."""
    i = 0
    if lines and lines[0].startswith("#!"): i = 1
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        if i < len(lines) and lines[i].lstrip().startswith("/*"):
            while i < len(lines) and "*/" not in lines[i]: i += 1
            i += 1
        return i
    q = None
    if i < len(lines):
        st = lines[i].lstrip()
        if st.startswith('"""') or st.startswith("'''"):
            q = st[:3]
            if st.count(q) >= 2 and len(st.strip()) > 3: return i + 1
            i += 1
            while i < len(lines) and q not in lines[i]: i += 1
            return i + 1
    return i

def strip_old(lines, tok):
    start = end = None
    for i, ln in enumerate(lines):
        if ln.startswith(tok) and "BEGIN NAV INDEX" in ln: start = i
        if ln.startswith(tok) and "END NAV INDEX" in ln: end = i; break
    if start is not None and end is not None and end >= start:
        del lines[start:end + 1]
        if start < len(lines) and lines[start].strip() == "": del lines[start]
    return lines

def build(path, lines=None):
    """Insert/refresh the NAV INDEX header on a single file. Idempotent.

    `lines` may be passed (raw readlines, header still present) to avoid re-reading
    when the caller already holds the buffer. Returns (ok, out_lines): ok=False and
    out_lines=[] if the file isn't decodable as utf-8 (skip, don't crash the run)."""
    ext = os.path.splitext(path)[1]
    tok = comment_token(path)
    if lines is None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, OSError) as e:
            print(f"navindex: skip (not utf-8) {os.path.basename(path)}: {e}", file=sys.stderr)
            return (False, [])
    lines = strip_old(list(lines), tok)
    ins = docstring_end(lines, ext)
    syms = [(n, lbl) for (n, lbl) in symbols(lines, ext) if n - 1 >= ins]
    block = [tok + " " + "=" * 22 + " BEGIN NAV INDEX " + "=" * 22 + "\n",
             tok + " " + TOP + "\n"]
    height = len(syms) + 4  # 2 header (begin+title) + each sym + 1 end + 1 trailing blank
    for n, lbl in syms:
        block.append(f"{tok}   L{n + height:<5} {lbl}\n")
    block.append(tok + " " + "=" * 23 + " END NAV INDEX " + "=" * 23 + "\n")
    block.append("\n")
    assert len(block) == height, f"height mismatch {len(block)} vs {height}"
    out = lines[:ins] + block + lines[ins:]
    with open(path, "w", encoding="utf-8", newline=file_eol(path)) as f:
        f.writelines(out)
    print(f"navindex: {os.path.basename(path)} ({len(syms)} symbols)")
    return (True, out)

# ---------------------------------------------------------------- folder driver

CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".ps1")
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "dist", "build", ".venv", "venv",
             ".pytest_cache", ".mypy_cache", "migrations", "alembic", "assets", "vendor",
             "volumes",   # 'volumes' = runtime bind-mount data (DB/redis/etc.) — never map
             "cache", ".cache"}  # generated tool caches (e.g. content-addressed AST dumps)
CACHE_VER = 3  # bump when symbol extraction changes, to invalidate stale cached symbol lists
HASHFILE = re.compile(r"^[0-9a-f]{32,}\.")  # content-addressed cache artifacts (sha-named blobs)
MAX_LINES = 8000  # default upper cap; overridable via --max-lines
DOC_EXT = {".md", ".json", ".html", ".htm", ".css", ".sql", ".yml", ".yaml",
           ".txt", ".toml", ".ini", ".cfg", ".sh"}  # .env intentionally excluded
MAP_NAME = "__navi__.md"
CACHE_NAME = ".navindex-cache.json"

def _is_vendor(path):
    b = os.path.basename(path).lower()
    return b.endswith((".min.js", ".bundle.js", ".module.js")) or b in {"three.js", "chart.js"}

def find_repo_root(start=None):
    """Nearest ancestor of `start` (default CWD) containing a .git entry; else the start dir.
    Detecting from CWD — not __file__ — is what makes the bundled skill portable across repos."""
    base = os.path.abspath(start or os.getcwd())
    cur = base
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return base
        cur = parent

def doc_descriptor(path, ext):
    """One-line descriptor for non-code files so they're still useful in the map."""
    try:
        if ext == ".md":
            for line in open(path, encoding="utf-8", errors="ignore"):
                s = line.strip()
                if s.startswith("#"):
                    return s.lstrip("# ").strip()[:90]
            return ""
        if ext == ".json":
            d = json.load(open(path, encoding="utf-8", errors="ignore"))
            if isinstance(d, dict):
                for k in ("name", "title", "id", "description"):
                    if k in d and isinstance(d[k], (str, int)):
                        return f"{k}: {str(d[k])[:70]}"
                return "keys: " + ", ".join(list(d.keys())[:8])
            if isinstance(d, list):
                return f"[{len(d)} items]"
    except Exception:
        return ""
    return ""

def body_hash(path, lines=None):
    """SHA1 of the file with any NAV INDEX block stripped — stable across header refreshes.
    Pass `lines` (raw readlines) to hash an already-read buffer without re-opening."""
    if lines is None:
        try:
            lines = open(path, encoding="utf-8").readlines()
        except (UnicodeDecodeError, OSError):
            return None
    lines = strip_old(list(lines), comment_token(path))
    return hashlib.sha1("".join(lines).encode("utf-8")).hexdigest()

def walk(root, depth):
    """Yield code/doc files within `depth` subfolder levels of root (depth 0 = root only)."""
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for cur, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if cur.count(os.sep) - base_depth > depth:
            dirs[:] = []
            continue
        for f in sorted(files):
            if f in (MAP_NAME, CACHE_NAME) or f.startswith("."):
                continue  # generated maps, the cache, and dotfiles are not source
            if HASHFILE.match(f):
                continue  # sha-named cache blob (e.g. <hash>.json) — generated junk, not source
            if os.path.splitext(f)[1] in CODE_EXT or os.path.splitext(f)[1] in DOC_EXT:
                yield os.path.join(cur, f)

def run_folder(root, rroot, args):
    cache_path = os.path.join(rroot, CACHE_NAME)
    cache = {}
    if os.path.exists(cache_path):
        try: cache = json.load(open(cache_path, encoding="utf-8"))
        except Exception: cache = {}
    if cache.get("__ver__") != CACHE_VER:  # extraction rules changed → cached symbols are stale
        cache = {"__ver__": CACHE_VER}

    is_global = os.path.abspath(root) == os.path.abspath(rroot)  # running at the repo root
    # The root tree is meant to be the COMPLETE universal index, so a global run ignores --depth
    # (a deep menu tree must not be silently truncated). Subfolder runs still honor --depth.
    eff_depth = 10**6 if is_global else args.depth
    files = list(walk(root, eff_depth))
    refreshed = skipped = 0
    seen = set()  # code rels processed this run — used to prune dead cache entries below
    entries = []  # (relpath, n_lines, [(line, label), ...], descriptor)

    def _clean_syms(lines, ext):
        return [(ln, lbl) for ln, lbl in symbols(lines, ext) if "NAV INDEX" not in lbl]

    for path in files:
        rel = os.path.relpath(path, rroot).replace(os.sep, "/")
        ext = os.path.splitext(path)[1]
        is_code = ext in CODE_EXT

        # ---- one read per file (reused for line count, hash, symbols, header build) ----
        raw, decoded = None, True
        try:
            raw = open(path, encoding="utf-8").readlines()
        except (UnicodeDecodeError, OSError):
            decoded = False
        if not decoded:
            if is_code:  # can't index a non-utf-8 source — warn once, skip entirely
                print(f"navindex: skip (not utf-8) {rel}", file=sys.stderr)
                continue
            raw = open(path, encoding="utf-8", errors="ignore").readlines()  # docs: lossy ok

        n_lines = len(raw)
        # line-count gates for whether a file is "considered" at all:
        #   < min_lines  → too trivial to index;  > max_lines → generated/huge, skip.
        if _is_vendor(path) or n_lines > args.max_lines or n_lines < args.min_lines:
            continue

        if is_code:
            seen.add(rel)
            h = body_hash(path, raw)
            cached = cache.get(rel)
            hit = isinstance(cached, dict) and cached.get("h") == h  # dict = new schema; str = stale
            need_header = (not args.map_only) and n_lines >= args.threshold

            if hit:
                syms = [tuple(x) for x in cached.get("s", [])]
                if need_header:
                    skipped += 1
            else:
                if need_header:
                    ok, out = build(path, raw)
                    if ok:
                        syms = _clean_syms(out, ext)  # post-build buffer: line nums incl. header
                        refreshed += 1
                    else:
                        syms = _clean_syms(raw, ext)
                else:
                    syms = _clean_syms(raw, ext)
                cache[rel] = {"h": h, "n": n_lines, "s": [[ln, lbl] for ln, lbl in syms]}

            if not args.no_map:
                entries.append((rel, n_lines, syms, ""))
        else:
            if not args.no_map:
                entries.append((rel, n_lines, [], doc_descriptor(path, ext)))

    # prune dead cache entries (deleted/renamed files) so the cache can't grow without bound.
    # SCOPED: only entries under the folder we just walked are candidates for removal — a subfolder
    # run must not evict entries for files it never visited.
    root_rel = os.path.relpath(root, rroot).replace(os.sep, "/")
    prefix = "" if root_rel == "." else root_rel + "/"
    pruned = {"__ver__": CACHE_VER}
    for k, v in cache.items():
        if k == "__ver__":
            continue
        in_scope = (not prefix) or k.startswith(prefix)
        if in_scope and k not in seen:
            continue  # was under this run's root but no longer exists → drop
        pruned[k] = v
    cache = pruned
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), indent=0)
    detailed = set()
    removed = 0
    if not args.no_map:
        detailed = write_map(root, rroot, args, entries)
        if is_global:
            # overwrite the root map with the global TREE (every folder -> filenames, no symbols)
            # so one read of the root gives the whole layout + which folder map to open next.
            write_tree(rroot, args, entries, detailed)
        keep = set(detailed) | ({"."} if is_global else set())
        removed = cleanup_stale_maps(root, rroot, keep)

    print(f"navindex: {len(files)} files | headers refreshed={refreshed} skipped={skipped}"
          + ("" if args.no_map else f" | maps written={len(detailed)}"
             + (f" | stale removed={removed}" if removed else "")
             + (" | + root tree" if is_global else "")))

def _is_generated_map(path):
    """True only for a __navi__.md the tool itself wrote (carries the navindex marker on line 2).
    Guards cleanup so a hand-written file of the same name is never deleted."""
    try:
        with open(path, encoding="utf-8") as f:
            f.readline()
            return "navindex" in f.readline()
    except OSError:
        return False

def cleanup_stale_maps(root, rroot, keep):
    """Delete navindex-generated __navi__.md files in folders that no longer earn one (now trivial,
    or now skipped — e.g. cache dirs). A stale map is worse than none: it points at wrong lines."""
    removed = 0
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]  # never descend these
        if MAP_NAME not in files:
            continue
        rel = os.path.relpath(cur, rroot).replace(os.sep, "/") or "."
        if rel in keep:
            continue
        p = os.path.join(cur, MAP_NAME)
        if _is_generated_map(p):
            os.remove(p)
            removed += 1
    return removed

def _is_detailed(items, args):
    """A folder earns its own __navi__.md only if it holds something worth a symbol map: a file
    with extracted symbols, or one big enough for an in-file header. Folders of trivial stubs
    (e.g. a 3-line main.ps1 with no functions) are folded into the root tree instead — emitting a
    near-empty map per leaf just multiplies files without adding navigation value."""
    return any(syms or n >= args.threshold for _, n, syms, _ in items)

def write_map(root, rroot, args, entries):
    """Write a __navi__.md only in directories that are 'detailed' (see _is_detailed): lists that
    folder's files -> symbol outline with exact line numbers, plus a breadcrumb to the root tree.
    Returns the set of POSIX-relative dirs that got a map (so the tree can mark them)."""
    by_dir = {}
    for rel, n_lines, syms, desc in entries:
        d = os.path.dirname(os.path.join(rroot, rel))
        by_dir.setdefault(d, []).append((rel, n_lines, syms, desc))

    detailed = set()
    for d, items in sorted(by_dir.items()):
        if not _is_detailed(items, args):
            continue  # trivial folder → no map; its files are listed in the root tree
        rel_dir = os.path.relpath(d, rroot).replace(os.sep, "/") or "."
        detailed.add(rel_dir)
        depth = 0 if rel_dir == "." else rel_dir.count("/") + 1
        up = ("../" * depth + MAP_NAME) if depth else None  # path back to the repo-root tree
        out = [f"# __navi__ · `{rel_dir}/` — {len(items)} files → symbols at exact line numbers",
               f"<!-- navindex · {datetime.date.today()} · DO NOT EDIT BY HAND; regen via navindex skill -->",
               *( [f"↑ repo tree: [`{up}`]({up})", ""] if up else [""] )]
        for rel, n_lines, syms, desc in sorted(items):
            fname = os.path.basename(rel)
            # descriptor only for non-code docs; for code the <sub> line below already carries the
            # symbols WITH line numbers, so repeating the first 6 names here is pure duplication.
            suffix = f" — {desc}" if desc else ""
            out.append(f"- **{fname}** ({n_lines} ln){suffix}")
            if syms:
                preview = "  ".join(f"L{ln}:{lbl}" for ln, lbl in syms[:24])
                out.append(f"  <sub>{preview}{' …' if len(syms) > 24 else ''}</sub>")
        out.append("")
        open(os.path.join(d, MAP_NAME), "w", encoding="utf-8").write("\n".join(out) + "\n")
    return detailed

def write_tree(rroot, args, entries, detailed):
    """Root-level GLOBAL index: every folder below -> the files it holds (names + line counts, NO
    symbols). The folder PATH is written ONCE per line; folders that have a detailed map carry a
    ' → __navi__.md' marker (open `<that path>/__navi__.md` for symbols). One read of this gives
    the whole layout; any symbol is then 2 reads away (this tree -> that folder's map)."""
    by_dir = {}
    for rel, n_lines, syms, desc in entries:
        d, _, name = rel.rpartition("/")  # d == "" for files directly in the repo root
        by_dir.setdefault(d, []).append((name, n_lines))
    nfiles = sum(len(v) for v in by_dir.values())
    out = [f"# __navi__ · repo tree — {nfiles} files in {len(by_dir)} folders",
           f"<!-- navindex · {datetime.date.today()} · DO NOT EDIT BY HAND; regen via navindex skill -->",
           "",
           "Universal index: every folder below -> the files it holds (names only). A "
           "`→ __navi__.md` marker means that folder has a symbol map — open `<that path>/"
           "__navi__.md` for exact line numbers (2 reads total: this tree -> folder map).",
           ""]
    for d in sorted(by_dir):
        rel_dir = d or "."
        marker = " → __navi__.md" if rel_dir in detailed else ""
        out.append(f"## `{rel_dir}/` ({len(by_dir[d])} files){marker}")
        out.append("  ".join(f"{name}({n})" for name, n in sorted(by_dir[d])))
        out.append("")
    open(os.path.join(rroot, MAP_NAME), "w", encoding="utf-8").write("\n".join(out) + "\n")

# ---------------------------------------------------------------- pre-commit hook

HOOK_MARK = "# navindex pre-commit hook"

def _wants_header(path, threshold):
    """--auto gate: touch only files that already carry a header, or are big enough to earn one.
    Keeps the pre-commit hook from stamping headers onto every tiny staged file."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, OSError):
        return False
    # ponytail: header is searched in the first 50 lines — enough past any shebang/docstring
    return len(lines) >= threshold or any("BEGIN NAV INDEX" in ln for ln in lines[:50])

def install_hook(rroot):
    """Write the repo's pre-commit hook: refresh headers on staged source files (--auto) and
    re-stage them, so committed headers can never go stale. Refuses to clobber a foreign hook.
    Hooks dir comes from `git rev-parse --git-path hooks`, so worktrees resolve to the main
    repo's .git/hooks (one install covers every worktree)."""
    import subprocess
    hooks = ""
    try:
        r = subprocess.run(["git", "rev-parse", "--git-path", "hooks"],
                           capture_output=True, text=True, cwd=rroot)
        if r.returncode == 0:
            hooks = os.path.join(rroot, r.stdout.strip())  # join keeps an absolute path as-is
    except OSError:
        pass
    if not hooks:
        hooks = os.path.join(rroot, ".git", "hooks")  # fallback: plain repo layout, no git CLI
        if not os.path.isdir(os.path.join(rroot, ".git")):
            sys.exit("navindex: no .git found — run from inside a git repo")
    os.makedirs(hooks, exist_ok=True)
    dst = os.path.join(hooks, "pre-commit")
    me = os.path.abspath(__file__).replace(os.sep, "/")
    if os.path.exists(dst) and HOOK_MARK not in open(dst, encoding="utf-8", errors="ignore").read():
        sys.exit(f"navindex: {dst} exists and isn't ours — add the navindex call to it manually")
    body = (
        "#!/bin/sh\n"
        f"{HOOK_MARK} (auto-generated; delete this file to uninstall)\n"
        "staged=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.(py|jsx?|tsx?|ps1)$')\n"
        "[ -z \"$staged\" ] && exit 0\n"
        f"echo \"$staged\" | tr '\\n' '\\0' | xargs -0 python \"{me}\" --auto || exit 1\n"
        "echo \"$staged\" | tr '\\n' '\\0' | xargs -0 git add\n")
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    os.chmod(dst, 0o755)
    print(f"navindex: pre-commit hook installed -> {dst}")

# ---------------------------------------------------------------- entrypoint

def main():
    ap = argparse.ArgumentParser(description="Universal NAV INDEX tool (per-file headers + folder maps).")
    ap.add_argument("paths", nargs="*", default=["."],
                    help="file(s) to header-refresh, OR a single folder to map (default: repo root)")
    ap.add_argument("--depth", type=int, default=6,
                    help="[folder] subfolder recursion depth (0 = root only). Ignored on a repo-root "
                         "run — the global tree is always full-depth so it can't be truncated.")
    ap.add_argument("--threshold", type=int, default=300, help="[folder] min lines for an in-file header")
    ap.add_argument("--min-lines", type=int, default=0,
                    help="[folder] skip files with fewer than N lines entirely (default 0 = keep all)")
    ap.add_argument("--max-lines", type=int, default=MAX_LINES,
                    help="[folder] skip files with more than N lines (generated/huge; default 8000)")
    ap.add_argument("--map-only", action="store_true", help="[folder] only (re)build __navi__.md, no headers")
    ap.add_argument("--no-map", action="store_true", help="[folder] only refresh headers, no __navi__.md")
    ap.add_argument("--install-hook", action="store_true",
                    help="install a git pre-commit hook that auto-refreshes headers on staged files")
    ap.add_argument("--auto", action="store_true",
                    help="[file] only touch files that already have a header or meet --threshold "
                         "(what the pre-commit hook passes)")
    args = ap.parse_args()
    paths = args.paths or ["."]
    rroot = find_repo_root()

    if args.install_hook:
        install_hook(rroot)
        return

    # FOLDER mode: a single positional that resolves to a directory (CWD- or repo-root-relative).
    if len(paths) == 1:
        p = paths[0]
        cand_cwd = os.path.abspath(p)
        cand_root = p if os.path.isabs(p) else os.path.join(rroot, p)
        folder = cand_cwd if os.path.isdir(cand_cwd) else (cand_root if os.path.isdir(cand_root) else None)
        if folder:
            run_folder(folder, rroot, args)
            return

    # FILE mode: header-refresh each path that is a file.
    any_file = False
    for p in paths:
        if os.path.isfile(p):
            if args.auto and not _wants_header(p, args.threshold):
                continue  # hook mode: small file without a header — leave it alone
            build(p); any_file = True
        else:
            print(f"navindex: skip (not a file or folder): {p}", file=sys.stderr)
    if not any_file and not args.auto:  # --auto skipping everything is success, not an error
        sys.exit("navindex: nothing to do (no valid file or folder given)")

if __name__ == "__main__":
    main()
