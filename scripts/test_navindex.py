"""Self-check for navindex.py — run: python scripts/test_navindex.py (exit 0 = ok)."""
import os, shutil, subprocess, sys, tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import navindex as nv

PY = (
    '"""doc."""\n'
    "import os\n"
    "class Svc:\n"
    "    def __init__(self):\n"
    "        pass\n"
    "    async def fetch(self):\n"
    "        def inner():\n"
    "            pass\n"
    "        return inner\n"
    "TOP_CONST = 1\n"
    "def solo():\n"
    "    pass\n"
)

TS = (
    "export interface Job { id: string }\n"
    "export type Mode = 'a' | 'b'\n"
    "export class Runner {\n"
    "  constructor(private q: Queue) {}\n"
    "  async run(job: Job): Promise<void> {\n"
    "    fetch(url).then(r => {\n"
    "      log(r)\n"
    "    })\n"
    "  }\n"
    "  onDone = async (r) => {\n"
    "  }\n"
    "}\n"
    "export function main() {}\n"
)

CS = (
    "using System;\n"
    "\n"
    "namespace App\n"
    "{\n"
    "    /// <summary>doc.</summary>\n"
    "    internal static class Runner\n"
    "    {\n"
    "        // ---------- dispatch ----------\n"
    "        public string Name { get; set; } = \"x\";\n"
    "        private static readonly Regex Rx = new Regex(\"a\");\n"
    "        public Runner(int q)\n"
    "        {\n"
    "        }\n"
    "        internal static Dictionary<string, object> Run(string[] args)\n"
    "        {\n"
    "            foreach (var a in args)\n"
    "            {\n"
    "                switch (a)\n"
    "                {\n"
    "                    case \"list-blocks\":\n"
    "                        return null;\n"
    "                    case \"BOOL\":\n"
    "                        return null;\n"
    "                }\n"
    "            }\n"
    "            if (args.Length > 0) return null;\n"
    "            return null;\n"
    "        }\n"
    "        public int Total => 1;\n"
    "    }\n"
    "}\n"
)

GO = (
    "//go:build windows\n"
    "\n"
    "// Package demo exercises Go NAV INDEX generation.\n"
    "package demo\n"
    "\n"
    "type Runner struct{}\n"
    "type Pair[T any] struct { A, B T }\n"
    "func NewRunner() *Runner { return &Runner{} }\n"
    "func (r *Runner) Run() {}\n"
    "func (p Pair[T]) Swap() Pair[T] { return Pair[T]{p.B, p.A} }\n"
)

MD = (
    "# Audit map\n"
    "text\n"
    "## Findings\n"
    "```md\n"
    "## Not a real section\n"
    "```\n"
    "### Detail intentionally omitted\n"
    "## Actions ##\n"
    "## C#\n"
)

def labels(text, ext):
    return [lbl for _, lbl in nv.symbols(text.splitlines(keepends=True), ext)]

def main():
    py = labels(PY, ".py")
    assert py == ["Svc", ".__init__", ".fetch", "TOP_CONST", "solo"], py  # inner() NOT indexed
    ts = labels(TS, ".ts")
    assert ts == ["Job", "Mode", "class Runner", ".constructor", ".run", ".onDone", "main"], ts
    # fetch(...) inside a method body must not appear (deeper than member indent)
    assert ".fetch" not in ts and "fetch" not in ts

    cs = labels(CS, ".cs")
    assert cs == ["class Runner", "dispatch", ".Name", ".Runner", ".Run",
                  'case "list-blocks"', ".Total"], cs
    # statements are never members, `= new Regex(` is a field, and a switch over data
    # values (`case "BOOL"`) is not a dispatch target
    for bad in (".if", ".foreach", ".switch", ".return", ".Regex", ".Rx", 'case "BOOL"'):
        assert bad not in cs, bad
    assert nv.comment_token("x.cs") == "//"
    go = labels(GO, ".go")
    assert go == ["type Runner", "type Pair", "NewRunner", "Runner.Run", "Pair.Swap"], go
    assert nv.comment_token("main.go") == "//"
    assert ".go" in nv.CODE_EXT
    assert nv.doc_symbols(MD.splitlines(keepends=True), ".md") == [
        (1, "Audit map"), (3, "Findings"), (8, "Actions"), (9, "C#")]
    assert nv.doc_symbols(MD.splitlines(keepends=True), ".json") == []
    assert nv.comment_token("notes.md") == "<!--"
    for name in ("README.md", "CONTRIBUTING.md", "LICENSE", "LICENSE.md", "SECURITY.md"):
        assert nv.header_exempt(name), name

    with tempfile.TemporaryDirectory() as d:
        # EOL preservation: LF stays LF, CRLF stays CRLF, across a header build
        lf, crlf = os.path.join(d, "lf.py"), os.path.join(d, "crlf.py")
        open(lf, "w", newline="\n").write(PY)
        open(crlf, "w", newline="\r\n").write(PY)
        nv.build(lf); nv.build(crlf)
        assert b"\r\n" not in open(lf, "rb").read()
        body = open(crlf, "rb").read()
        assert b"\r\n" in body and b"\n" not in body.replace(b"\r\n", b"")

        # idempotency: second build is byte-identical
        before = open(lf, "rb").read()
        nv.build(lf)
        assert open(lf, "rb").read() == before

        # header line numbers point at the real symbols
        lines = open(lf, encoding="utf-8").read().splitlines()
        for entry in [l for l in lines if l.startswith("#   L")]:
            n, lbl = entry[5:].split(None, 1)
            target = lines[int(n) - 1]
            assert lbl.lstrip(".") in target, (entry, target)

        # --auto gate: small headerless file untouched, headered file refreshed
        small = os.path.join(d, "small.py")
        open(small, "w", newline="\n").write("def a():\n    pass\n")
        assert not nv._wants_header(small, 300)
        assert nv._wants_header(lf, 300)  # has a header now, size irrelevant

        # C# header: '//' token, inserted below a leading /* */ banner, idempotent
        cs_path = os.path.join(d, "app.cs")
        open(cs_path, "w", newline="\n").write("/* license */\n" + CS)
        nv.build(cs_path)
        text = open(cs_path, encoding="utf-8").read()
        assert text.startswith("/* license */\n// ====="), text[:80]
        first = open(cs_path, "rb").read()
        nv.build(cs_path)
        assert open(cs_path, "rb").read() == first

        # Go: preserve build constraints and package docs, then insert a valid // header after
        # the package clause. gofmt is an optional stronger syntax check when available.
        go_path = os.path.join(d, "demo.go")
        open(go_path, "w", newline="\n").write(GO)
        nv.build(go_path)
        go_before = open(go_path, "rb").read()
        nv.build(go_path)
        assert open(go_path, "rb").read() == go_before
        go_lines = open(go_path, encoding="utf-8").read().splitlines()
        package_line = go_lines.index("package demo")
        assert go_lines[0] == "//go:build windows"
        assert go_lines[package_line - 1] == "// Package demo exercises Go NAV INDEX generation."
        assert go_lines[package_line + 2].startswith("// ===")
        for entry in [line for line in go_lines if line.startswith("//   L")]:
            n, lbl = entry[6:].split(None, 1)
            target = go_lines[int(n) - 1]
            assert lbl.split(".")[-1].replace("type ", "") in target, (entry, target)
        if gofmt := shutil.which("gofmt"):
            subprocess.run([gofmt, "-w", go_path], check=True)

        # Markdown owns its outline: the folder map only points to this hidden header range.
        md_path = os.path.join(d, "audit.md")
        open(md_path, "w", newline="\n").write(MD)
        nv.build(md_path)
        md_before = open(md_path, "rb").read()
        nv.build(md_path)
        assert open(md_path, "rb").read() == md_before
        md_lines = open(md_path, encoding="utf-8").read().splitlines()
        assert nv.nav_header_range(md_lines, "<!--") == "NAV L1-L7"
        header = "\n".join(md_lines[:7])
        assert "Audit map" in header and "Actions" in header
        assert "Not a real section" not in header
        assert md_lines[8] == "# Audit map"
        assert nv._wants_header(md_path, 300)

        # YAML front matter must remain first; the NAV header starts after it and its blank line.
        front = os.path.join(d, "skill.md")
        open(front, "w", newline="\n").write("---\nname: demo\n---\n\n# Front\n")
        nv.build(front)
        front_lines = open(front, encoding="utf-8").read().splitlines()
        assert front_lines[:4] == ["---", "name: demo", "---", ""]
        assert nv.nav_header_range(front_lines, "<!--") == "NAV L5-L8"
        assert front_lines[9] == "# Front"

        # Public repository documents are explicit exceptions, even in direct file mode.
        security = os.path.join(d, "SECURITY.md")
        open(security, "w", newline="\n").write("# Security\n")
        nv.build(security)
        assert "BEGIN NAV INDEX" not in open(security, encoding="utf-8").read()

    with tempfile.TemporaryDirectory() as d:
        # gitignored paths stay out of the walk (and --include-ignored puts them back)
        run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True)
        run("init", "-q")
        open(os.path.join(d, ".gitignore"), "w").write("payload/\nsecret.py\n")
        os.mkdir(os.path.join(d, "payload"))
        for rel in ("keep.py", "secret.py", "payload/leak.py"):
            open(os.path.join(d, rel), "w").write("def f():\n    pass\n")
        ign = nv.git_ignored(d)
        got = {os.path.relpath(p, d).replace(os.sep, "/") for p in nv.walk(d, 6, d, ign)}
        assert got == {"keep.py"}, got
        allf = {os.path.relpath(p, d).replace(os.sep, "/") for p in nv.walk(d, 6, d)}
        assert allf == {"keep.py", "secret.py", "payload/leak.py"}, allf

    with tempfile.TemporaryDirectory() as d:
        # Folder mode is stable; Markdown headings stay in-file, not in the folder map.
        repo = os.path.join(d, "repo")
        pkg = os.path.join(repo, "pkg")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(pkg)
        open(os.path.join(pkg, "demo.go"), "w", newline="\n").write(GO)
        open(os.path.join(pkg, "audit.md"), "w", newline="\n").write(MD)
        old = ("# ====================== BEGIN NAV INDEX ======================\n"
               "# NAV INDEX — old\n"
               "#   L6     Public\n"
               "# ======================= END NAV INDEX =======================\n\n"
               "# Public\n")
        readme = os.path.join(repo, "README.md")
        open(readme, "w", encoding="utf-8", newline="\n").write(old)
        open(os.path.join(repo, "LICENSE"), "w", newline="\n").write("MIT\n")
        assert nv._wants_header(readme, 300)  # cleanup of an old generated header
        args = SimpleNamespace(depth=6, threshold=1, min_lines=0, max_lines=8000,
                               map_only=False, no_map=False, include_ignored=False)
        nv.run_folder(repo, repo, args)
        first_tree = open(os.path.join(repo, nv.MAP_NAME), "rb").read()
        first_map = open(os.path.join(pkg, nv.MAP_NAME), "rb").read()
        assert b"audit.md** (17 ln) \xe2\x80\x94 NAV L1-L7" in first_map
        assert b"Audit map" not in first_map and b"Actions" not in first_map
        assert b"audit.md(17; NAV L1-L7)" in first_tree
        assert b"README.md(1)" in first_tree and b"LICENSE(1)" in first_tree
        assert b"README.md(1; NAV" not in first_tree
        assert open(readme, encoding="utf-8").read() == "# Public\n"
        assert not nv._wants_header(readme, 300)
        nv.run_folder(repo, repo, args)
        assert open(os.path.join(repo, nv.MAP_NAME), "rb").read() == first_tree
        assert open(os.path.join(pkg, nv.MAP_NAME), "rb").read() == first_map

    print("test_navindex: all checks passed")

if __name__ == "__main__":
    main()
