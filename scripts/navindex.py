"""navindex — one universal NAV INDEX tool (per-file headers + folder maps).

Two modes, auto-detected from the positional argument:
  • FILE mode   — pass one or more files → refresh each file's NAV INDEX header (any size).
  • FOLDER mode — pass a single folder (or nothing → repo root) → (re)build that folder's
                  __navi__.md map AND refresh headers on large files in one pass.

Portable: the repo root is detected from the current working directory (nearest ancestor with a
.git, else CWD) — NOT from where this script lives — so the bundled skill works in any repo. Run
it from inside the target repo.

Idempotent: re-running rebuilds the header/map in place (the old block is stripped first), so it
never stacks. Supported code: .py, .js/.jsx/.ts/.tsx, .go, .ps1, .cs.

Gitignored paths are skipped in a git repo (one `git ls-files` call per run) — a generated map
must not leak the contents of folders the repo deliberately keeps out. `--include-ignored` opts out.

Usage:
  python navindex.py path/to/file.py [more.py ...]        # FILE mode
  python navindex.py backend/src --depth 4                # FOLDER mode
  python navindex.py                                       # FOLDER mode on the repo root
  python navindex.py --install-hook                        # pre-commit hook: headers never stale
Folder flags: --depth N (recursion, default 6) · --threshold N (min lines for a header,
default 300) · --min-lines N (skip files shorter than N entirely, default 0) · --max-lines N
(skip files longer than N — generated/huge, default 8000) · --map-only (only __navi__.md) ·
--no-map (only headers) · --include-ignored (map gitignored paths too). File flags: --auto (only
files already carrying a header or at/above --threshold — what the pre-commit hook passes).
"""
# ====================== BEGIN NAV INDEX ======================
# NAV INDEX — auto-generated symbol map (refresh via the navindex skill)
#   L84    TOP
#   L85    HEADER_EXEMPT_DOCS
#   L88    per-file core
#   L90    comment_token
#   L95    header_exempt
#   L98    comment_line
#   L101   file_eol
#   L113   JS_KW
#   L116   _go_receiver_name
#   L121   CS_KW
#   L122   CS_MOD
#   L128   CS_TYPE
#   L129   CS_METHOD
#   L130   CS_PROP
#   L131   CS_CASE
#   L140   CS_CASE_VERB
#   L142   symbols
#   L242   docstring_end
#   L275   strip_old
#   L302   strip_headers
#   L314   nav_header_range
#   L325   build
#   L375   folder driver
#   L377   CODE_EXT
#   L378   SKIP_DIRS
#   L382   CACHE_VER
#   L383   HASHFILE
#   L384   MAX_LINES
#   L385   DOC_EXT
#   L387   MAP_NAME
#   L388   CACHE_NAME
#   L390   _is_vendor
#   L394   find_repo_root
#   L407   doc_symbols
#   L423   body_hash
#   L434   git_ignored
#   L454   walk
#   L484   run_folder
#   L601   _is_generated_map
#   L611   cleanup_stale_maps
#   L628   _is_detailed
#   L635   write_map
#   L666   write_tree
#   L692   pre-commit hook
#   L694   HOOK_MARK
#   L696   _wants_header
#   L710   install_hook
#   L745   entrypoint
#   L747   main
# ======================= END NAV INDEX =======================

import argparse, hashlib, json, os, re, subprocess, sys, datetime

TOP = "NAV INDEX — auto-generated symbol map (refresh via the navindex skill)"
HEADER_EXEMPT_DOCS = frozenset({"readme.md", "contributing.md", "license", "license.md",
                                "security.md"})

# ---------------------------------------------------------------- per-file core

def comment_token(path):
    if os.path.splitext(path)[1].lower() == ".md":
        return "<!--"
    return "//" if os.path.splitext(path)[1].lower() in (".js", ".jsx", ".ts", ".tsx", ".go", ".cs") else "#"

def header_exempt(path):
    return os.path.basename(path).lower() in HEADER_EXEMPT_DOCS

def comment_line(tok, body):
    return f"<!-- {body} -->\n" if tok == "<!--" else f"{tok} {body}\n"

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

def _go_receiver_name(spec):
    """Return the base receiver type from `r *Runner`, `*Runner`, or `p Pair[T]`."""
    m = re.search(r"(?:^|\s)\*?([A-Za-z_]\w*)(?:\s*\[[^]]+\])?\s*$", spec.strip())
    return m.group(1) if m else ""

CS_KW = JS_KW | {"foreach", "using", "lock", "fixed", "when", "throw", "checked", "unchecked"}
CS_MOD = (r"(?:(?:public|private|protected|internal|static|virtual|override|abstract|sealed|"
          r"async|extern|unsafe|new|partial|readonly|const|event|volatile)\s+)")
# A member line must carry at least one modifier (CS_MOD+), which is what keeps statements
# (`if (x)`, `foreach (var y in z)`) out — they live deeper than the member indent anyway, but
# the modifier is the cheap structural guard. `[^()=]*?` = the return type: barring '=' stops
# `static readonly Regex Rx = new Regex(...)` from being read as a method named Regex.
CS_TYPE = re.compile(r"^\s*" + CS_MOD + r"*(class|struct|interface|enum|record)\s+(\w+)")
CS_METHOD = re.compile(r"^\s*" + CS_MOD + r"+(?:[^()=]*?\s+)?(\w+)\s*(?:<[^<>()]*>)?\s*\(")
CS_PROP = re.compile(r"^\s*" + CS_MOD + r"+(?:[^()=]*?\s+)?(\w+)\s*(?:\{\s*(?:get|set|init)\b|=>)")
CS_CASE = re.compile(r'^\s*case\s+"([^"]+)":')  # string-literal dispatch (CLI verb tables)
# Only all-lowercase literals index: a CLI verb is lowercase by universal convention
# (`list-blocks`, `gen-profinet`), while a switch over data values carries capitals
# (`case "Coil"`, `case "BOOL"`, `case "LEITURA_ALTA"`) and is not a navigation target.
# Measured on a 10.7k-line C# CLI: keeps 77/77 real verbs, drops all 25 data cases.
# ponytail: convention bet, not a parse — a repo dispatching on PascalCase literals
# (`case "OrderPlaced":`, event routing) loses those from the index. Only the case
# labels; methods/types are unaffected. Fix if it ever bites: also accept PascalCase
# of 2+ words, which keeps single-word data values (`Coil`, `Move`, `Eq`) out.
CS_CASE_VERB = re.compile(r"^[a-z][a-z0-9_-]*$")

def symbols(lines, ext):
    if ext == ".md":
        return doc_symbols(lines, ext)
    out = []
    in_class = False   # inside a top-level class body → members index as ".name"
    m_indent = None    # member indent = indent of the FIRST non-blank line after `class`;
                       # only lines at exactly that indent are members, so statements inside
                       # method bodies (always deeper) can never false-positive as methods.
    for i, ln in enumerate(lines, 1):
        s = ln.rstrip("\n")
        ind = len(s) - len(s.lstrip())
        if in_class and s.strip() and m_indent is None and not (ext == ".cs" and s.strip() == "{"):
            m_indent = ind  # C#: the brace under `class X` sits at the CLASS indent, not the member's
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
        elif ext == ".go":
            m = re.match(r"^type\s+([A-Za-z_]\w*)\b", s)
            if m:
                out.append((i, "type " + m.group(1)))
                continue
            m = re.match(r"^func\s+\(([^)]*)\)\s+([A-Za-z_]\w*)\s*\(", s)
            if m:
                receiver = _go_receiver_name(m.group(1))
                out.append((i, f"{receiver}.{m.group(2)}" if receiver else m.group(2)))
            elif (m := re.match(r"^func\s+([A-Za-z_]\w*)\s*(?:\[[^]]+\]\s*)?\(", s)):
                out.append((i, m.group(1)))
            elif re.match(r"^// ?[-=]{3,}", s):
                lbl = s.lstrip("/ -=")[:70]
                if lbl: out.append((i, lbl))
        elif ext == ".cs":
            m = CS_TYPE.match(s)
            if m:
                out.append((i, f"{m.group(1)} {m.group(2)}"))
                # A NESTED type keeps the outer member indent: resetting it here would make every
                # member after the nested class measure against the nested body and vanish.
                if m_indent is None or ind < m_indent:
                    in_class, m_indent = True, None
                continue
            if in_class and ind == m_indent and (
                    (mm := CS_METHOD.match(s)) or (mm := CS_PROP.match(s))):
                # ponytail: single-line signatures only — a param list spanning lines is missed
                if mm.group(1) not in CS_KW: out.append((i, "." + mm.group(1)))
            elif (mm := CS_CASE.match(s)) and CS_CASE_VERB.match(mm.group(1)):
                # `case "verb":` is the jump target in a CLI dispatch switch, wherever it is
                # nested — so this one is NOT gated on the member indent.
                out.append((i, f'case "{mm.group(1)}"'))
            elif re.match(r"^\s*// ?[-=]{3,}", s):
                lbl = s.strip().lstrip("/ -=").rstrip(" -=")[:70]
                if lbl: out.append((i, lbl))
        elif ext in (".ps1", ".psm1"):
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
    if ext == ".md" and lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                end = j + 1
                return end + 1 if end < len(lines) and not lines[end].strip() else end
        return 0
    if ext == ".go":
        # Build constraints and package documentation must stay before `package`; inserting the
        # header after the package clause preserves both Go semantics and godoc association.
        for j, line in enumerate(lines):
            if re.match(r"^package\s+[A-Za-z_]\w*\s*$", line.rstrip("\r\n")):
                return j + 2 if j + 1 < len(lines) and not lines[j + 1].strip() else j + 1
        return 0
    if ext in (".js", ".jsx", ".ts", ".tsx", ".cs"):
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
    # Marker lines are `<tok> ==== BEGIN/END NAV INDEX ====`. A symbol ENTRY that mentions the
    # marker (`<tok>   L60    END NAV INDEX ...`) must NOT match, or the strip truncates
    # mid-header and leaves the tail behind as an orphan block that stacks forever.
    def marker(ln, kind):
        return (ln.startswith(tok) and f"{kind} NAV INDEX" in ln
                and ln[len(tok):].lstrip().startswith("="))
    while True:
        start = end = None
        for i, ln in enumerate(lines):
            if start is None and marker(ln, "BEGIN"): start = i
            if marker(ln, "END"): end = i; break
        if end is None: return lines
        if start is None or start > end:
            # orphan tail (END without BEGIN, left by older buggy strips): walk back over
            # its entry/title lines so the whole block dies, not just the END line
            start = end
            while start > 0:
                p = lines[start - 1]
                body = p[len(tok):].lstrip() if p.startswith(tok) else None
                if body is not None and (re.match(r"L\d+\s", body) or "NAV INDEX" in p):
                    start -= 1
                else:
                    break
        del lines[start:end + 1]
        if start < len(lines) and lines[start].strip() == "": del lines[start]

def strip_headers(lines, path):
    """Remove current and legacy NAV blocks for a file.

    Markdown used ``#`` before gaining hidden HTML-comment headers, so refreshes must clean both
    forms. The marker text is navindex-specific, avoiding accidental removal of ordinary headings.
    """
    tokens = ("<!--", "#") if os.path.splitext(path)[1].lower() == ".md" else (comment_token(path),)
    out = list(lines)
    for tok in tokens:
        out = strip_old(out, tok)
    return out

def nav_header_range(lines, tok):
    start = end = None
    for i, line in enumerate(lines, 1):
        body = line[len(tok):].lstrip() if line.startswith(tok) else ""
        if body.startswith("=") and "BEGIN NAV INDEX" in line:
            start = i
        if start and body.startswith("=") and "END NAV INDEX" in line:
            end = i
            break
    return f"NAV L{start}-L{end}" if start and end else "NAV missing"

def build(path, lines=None):
    """Insert/refresh the NAV INDEX header on a single file. Idempotent.

    `lines` may be passed (raw readlines, header still present) to avoid re-reading
    when the caller already holds the buffer. Returns (ok, out_lines): ok=False and
    out_lines=[] if the file isn't decodable as utf-8 (skip, don't crash the run)."""
    ext = os.path.splitext(path)[1].lower()
    tok = comment_token(path)
    if lines is None:
        try:
            # utf-8-sig: um BOM lido como utf-8 vira '﻿' na linha 1 — o header seria
            # inserido ANTES dele, deixando o BOM no MEIO do arquivo (quebra o parse do PS)
            with open(path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, OSError) as e:
            print(f"navindex: skip (not utf-8) {os.path.basename(path)}: {e}", file=sys.stderr)
            return (False, [])
    try:
        with open(path, "rb") as f:
            had_bom = f.read(3) == b"\xef\xbb\xbf"
    except OSError:
        had_bom = False
    if lines and lines[0].startswith("﻿"):  # caller read without -sig
        lines[0] = lines[0][1:]
    if header_exempt(path):
        out = strip_headers(lines, path)
        if out != lines:
            with open(path, "w", encoding="utf-8-sig" if had_bom else "utf-8",
                      newline=file_eol(path)) as f:
                f.writelines(out)
        print(f"navindex: {os.path.basename(path)} (header-exempt)")
        return (True, out)
    lines = strip_headers(lines, path)
    ins = docstring_end(lines, ext)
    syms = [(n, lbl) for (n, lbl) in symbols(lines, ext) if n - 1 >= ins and "NAV INDEX" not in lbl]
    block = [comment_line(tok, "=" * 22 + " BEGIN NAV INDEX " + "=" * 22),
             comment_line(tok, TOP)]
    height = len(syms) + 4  # 2 header (begin+title) + each sym + 1 end + 1 trailing blank
    for n, lbl in syms:
        block.append(comment_line(tok, f"  L{n + height:<5} {lbl}"))
    block.append(comment_line(tok, "=" * 23 + " END NAV INDEX " + "=" * 23))
    block.append("\n")
    assert len(block) == height, f"height mismatch {len(block)} vs {height}"
    out = lines[:ins] + block + lines[ins:]
    # preserva o BOM original: PS5 lê utf-8 sem BOM como ANSI (mojibake nos acentos)
    with open(path, "w", encoding="utf-8-sig" if had_bom else "utf-8", newline=file_eol(path)) as f:
        f.writelines(out)
    print(f"navindex: {os.path.basename(path)} ({len(syms)} symbols)")
    return (True, out)

# ---------------------------------------------------------------- folder driver

CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".ps1", ".psm1", ".cs")
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "dist", "build", ".venv", "venv",
             ".pytest_cache", ".mypy_cache", "migrations", "alembic", "assets", "vendor",
             "volumes",   # 'volumes' = runtime bind-mount data (DB/redis/etc.) — never map
             "cache", ".cache"}  # generated tool caches (e.g. content-addressed AST dumps)
CACHE_VER = 8  # bump when symbol/header extraction changes, to invalidate stale cached lists
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

def doc_symbols(lines, ext):
    """Return major Markdown headings for its in-file NAV header, ignoring fenced examples."""
    if ext != ".md":
        return []
    out, fence = [], None
    for i, line in enumerate(lines, 1):
        s = line.rstrip("\r\n")
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", s)
        if marker:
            token = marker.group(1)[0]
            fence = None if fence == token else (token if fence is None else fence)
            continue
        if fence is None and (m := re.match(r"^\s{0,3}#{1,2}\s+(.+?)\s*$", s)):
            out.append((i, re.sub(r"\s+#+\s*$", "", m.group(1)).strip()))
    return out

def body_hash(path, lines=None):
    """SHA1 of the file with any NAV INDEX block stripped — stable across header refreshes.
    Pass `lines` (raw readlines) to hash an already-read buffer without re-opening."""
    if lines is None:
        try:
            lines = open(path, encoding="utf-8-sig").readlines()
        except (UnicodeDecodeError, OSError):
            return None
    lines = strip_headers(lines, path)
    return hashlib.sha1("".join(lines).encode("utf-8")).hexdigest()

def git_ignored(rroot):
    """POSIX-relative paths git ignores under `rroot` — a wholly ignored folder collapses to one
    entry with a trailing '/'. ONE subprocess per run: `git check-ignore` per file would be
    thousands of processes. `core.quotePath=false` keeps non-ASCII folder names readable instead
    of octal-escaped, or the prefix match below would never hit them.

    Why this exists: a generated map is committed, so it must not enumerate what the repo
    deliberately keeps out — gitignored payload folders leak names (customer projects, exports)
    into a public repo. Empty set if git is missing or this isn't a repo: mapping a bit too much
    beats crashing."""
    try:
        r = subprocess.run(["git", "-c", "core.quotePath=false", "-C", rroot, "ls-files",
                            "--others", "--ignored", "--exclude-standard", "--directory"],
                           capture_output=True, text=True)
    except OSError:
        return set()
    if r.returncode != 0:
        return set()
    return {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}

def walk(root, depth, rroot=None, ignored=frozenset()):
    """Yield code/doc files within `depth` subfolder levels of root (depth 0 = root only),
    skipping anything in `ignored` (see git_ignored)."""
    root = os.path.abspath(root)
    rroot = os.path.abspath(rroot or root)
    base_depth = root.rstrip(os.sep).count(os.sep)

    def rel(p):
        return os.path.relpath(p, rroot).replace(os.sep, "/")

    for cur, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if ignored:
            # Pruning at the first ignored level is enough: os.walk is top-down, so its children
            # (which git collapsed into that one entry) are never visited.
            dirs[:] = [d for d in dirs if rel(os.path.join(cur, d)) + "/" not in ignored]
        if cur.count(os.sep) - base_depth > depth:
            dirs[:] = []
            continue
        for f in sorted(files):
            if ignored and rel(os.path.join(cur, f)) in ignored:
                continue  # ignored file sitting in a tracked folder
            if f in (MAP_NAME, CACHE_NAME) or f.startswith("."):
                continue  # generated maps, the cache, and dotfiles are not source
            if HASHFILE.match(f):
                continue  # sha-named cache blob (e.g. <hash>.json) — generated junk, not source
            if (os.path.splitext(f)[1].lower() in CODE_EXT or os.path.splitext(f)[1].lower() in DOC_EXT
                    or f.lower() in HEADER_EXEMPT_DOCS):
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
    ignored = set() if args.include_ignored else git_ignored(rroot)
    files = list(walk(root, eff_depth, rroot, ignored))
    refreshed = skipped = 0
    seen = set()  # code rels processed this run — used to prune dead cache entries below
    entries = []  # (relpath, n_lines, [(line, label), ...], compact map note)

    def _clean_syms(lines, ext):
        return [(ln, lbl) for ln, lbl in symbols(lines, ext) if "NAV INDEX" not in lbl]

    for path in files:
        rel = os.path.relpath(path, rroot).replace(os.sep, "/")
        ext = os.path.splitext(path)[1].lower()
        is_code = ext in CODE_EXT
        is_markdown = ext == ".md"
        is_exempt = header_exempt(path)
        is_indexed = is_code or (is_markdown and not is_exempt)

        # ---- one read per file (reused for line count, hash, symbols, header build) ----
        raw, decoded = None, True
        try:
            raw = open(path, encoding="utf-8-sig").readlines()
        except (UnicodeDecodeError, OSError):
            decoded = False
        if not decoded:
            if is_indexed:  # can't safely rewrite a non-utf-8 indexed file
                print(f"navindex: skip (not utf-8) {rel}", file=sys.stderr)
                continue
            raw = open(path, encoding="utf-8", errors="ignore").readlines()  # docs: lossy ok

        n_lines = len(raw)
        # line-count gates for whether a file is "considered" at all:
        #   < min_lines  → too trivial to index;  > max_lines → generated/huge, skip.
        if _is_vendor(path) or n_lines > args.max_lines or n_lines < args.min_lines:
            continue

        if is_indexed:
            seen.add(rel)
            h = body_hash(path, raw)
            cached = cache.get(rel)
            hit = isinstance(cached, dict) and cached.get("h") == h  # dict = new schema; str = stale
            need_header = (not args.map_only) and (is_markdown or n_lines >= args.threshold)
            has_header = nav_header_range(raw, comment_token(path)) != "NAV missing"

            if hit and (not need_header or has_header):
                syms = [tuple(x) for x in cached.get("s", [])]
                if need_header:
                    skipped += 1
            else:
                if need_header:
                    ok, out = build(path, raw)
                    if ok:
                        raw = out
                        n_lines = len(out)
                        syms = _clean_syms(out, ext)  # post-build buffer: line nums incl. header
                        refreshed += 1
                    else:
                        syms = _clean_syms(raw, ext)
                else:
                    syms = _clean_syms(raw, ext)
                cache[rel] = {"h": h, "n": n_lines, "s": [[ln, lbl] for ln, lbl in syms]}

            if not args.no_map:
                note = nav_header_range(raw, comment_token(path)) if is_markdown else ""
                entries.append((rel, n_lines, [] if is_markdown else syms, note))
        else:
            if is_exempt and not args.map_only and strip_headers(raw, path) != raw:
                ok, out = build(path, raw)
                if ok:
                    raw, n_lines = out, len(out)
                    refreshed += 1
            if not args.no_map:
                entries.append((rel, n_lines, [], ""))

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
    """Write a __navi__.md only in directories that are 'detailed' (see _is_detailed): lists code
    symbols and only the in-file NAV range for Markdown, plus a breadcrumb to the root tree.
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
        out = [f"# __navi__ · `{rel_dir}/` — {len(items)} files → code symbols / text NAV ranges",
               f"<!-- navindex · {datetime.date.today()} · DO NOT EDIT BY HAND; regen via navindex skill -->",
               *( [f"↑ repo tree: [`{up}`]({up})", ""] if up else [""] )]
        for rel, n_lines, syms, desc in sorted(items):
            fname = os.path.basename(rel)
            suffix = f" — {desc}" if desc else ""
            out.append(f"- **{fname}** ({n_lines} ln){suffix}")
            if syms:
                preview = "  ".join(f"L{ln}:{lbl}" for ln, lbl in syms[:24])
                out.append(f"  <sub>{preview}{' …' if len(syms) > 24 else ''}</sub>")
        out.append("")
        open(os.path.join(d, MAP_NAME), "w", encoding="utf-8").write("\n".join(out).rstrip() + "\n")
    return detailed

def write_tree(rroot, args, entries, detailed):
    """Root-level GLOBAL index: every folder below -> files and line counts; Markdown adds only its
    in-file NAV range. The folder PATH is written ONCE; folders with a detailed code map carry a
    ' → __navi__.md' marker (open `<that path>/__navi__.md` for symbols). One read of this gives
    the whole layout; any symbol is then 2 reads away (this tree -> that folder's map)."""
    by_dir = {}
    for rel, n_lines, syms, desc in entries:
        d, _, name = rel.rpartition("/")  # d == "" for files directly in the repo root
        by_dir.setdefault(d, []).append((name, n_lines, desc))
    nfiles = sum(len(v) for v in by_dir.values())
    out = [f"# __navi__ · repo tree — {nfiles} files in {len(by_dir)} folders",
           f"<!-- navindex · {datetime.date.today()} · DO NOT EDIT BY HAND; regen via navindex skill -->",
           "",
           "Universal index: every folder below -> filenames; Markdown adds only its in-file NAV "
           "range. A `→ __navi__.md` marker means that folder has a detailed code map — open "
           "`<that path>/__navi__.md` for exact symbol lines.",
           ""]
    for d in sorted(by_dir):
        rel_dir = d or "."
        marker = " → __navi__.md" if rel_dir in detailed else ""
        out.append(f"## `{rel_dir}/` ({len(by_dir[d])} files){marker}")
        out.append("  ".join(f"{name}({n}{'; ' + desc if desc else ''})"
                            for name, n, desc in sorted(by_dir[d])))
        out.append("")
    open(os.path.join(rroot, MAP_NAME), "w", encoding="utf-8").write("\n".join(out).rstrip() + "\n")

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
    has_header = any("BEGIN NAV INDEX" in ln for ln in lines[:50])
    if header_exempt(path):
        return has_header  # one cleanup pass if an older version inserted a header
    return path.lower().endswith(".md") or len(lines) >= threshold or has_header

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
        "staged=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.(go|py|jsx?|tsx?|ps1|cs|md)$')\n"
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
    ap.add_argument("--include-ignored", action="store_true",
                    help="[folder] also map gitignored paths (default: skip them, so a committed "
                         "map can't leak the contents of folders the repo keeps out)")
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
