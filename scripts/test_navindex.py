"""Self-check for navindex.py — run: python scripts/test_navindex.py (exit 0 = ok)."""
import os, subprocess, sys, tempfile

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

    print("test_navindex: all checks passed")

if __name__ == "__main__":
    main()
