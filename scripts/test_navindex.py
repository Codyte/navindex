"""Self-check for navindex.py — run: python scripts/test_navindex.py (exit 0 = ok)."""
import os, sys, tempfile

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

def labels(text, ext):
    return [lbl for _, lbl in nv.symbols(text.splitlines(keepends=True), ext)]

def main():
    py = labels(PY, ".py")
    assert py == ["Svc", ".__init__", ".fetch", "TOP_CONST", "solo"], py  # inner() NOT indexed
    ts = labels(TS, ".ts")
    assert ts == ["Job", "Mode", "class Runner", ".constructor", ".run", ".onDone", "main"], ts
    # fetch(...) inside a method body must not appear (deeper than member indent)
    assert ".fetch" not in ts and "fetch" not in ts

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

    print("test_navindex: all checks passed")

if __name__ == "__main__":
    main()
