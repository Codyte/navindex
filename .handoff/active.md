# Handoff · navindex · 2026-08-11

## Goal
C# support and `.gitignore` filtering in `navindex.py` — delivered and on `origin/main`. What
remains is running it on other repos and the known edges listed in Open.

## State
- HEAD: `4ad0dfc` (`feat: index C# and skip gitignored paths`), pushed. Working tree clean.
- Live state: nothing running. The real consumer of the change is the `Codyte/Tia-Portal-CLI` repo
  (`~/.agents/skills/tia`, HEAD `f2adeba`), which already deleted the parallel generator
  `scripts/navi-cs.ps1` and depends on this behavior — a regression here breaks navigation there.
- Done:
  - **C# (`.cs`)**: `CODE_EXT`, `comment_token` (`//`), `docstring_end` (JS branch, the header goes
    below a `/* */` banner), a new branch in `symbols()` with `CS_TYPE`/`CS_METHOD`/`CS_PROP`/
    `CS_CASE`, `CS_KW`, and the pre-commit hook now picks up `.cs`.
  - **`git_ignored()` + filter in `walk()`**: 1 subprocess per run, `--include-ignored` turns it off.
  - `CACHE_VER` 4 → 5. New tests (C# symbols, idempotent header with BOM/EOL, walk with
    `.gitignore` in a temporary repo). SKILL.md, README.md and `references/internals.md` updated.
  - Real validation: 17 `.cs` files of the tia repo headerized, `pwsh scripts/rebuild.ps1` **ALL PASS**,
    a 3rd run changes no byte (idempotence checked with `md5sum -c`).
- In progress: nothing.

## Decisions (and why)
- **A C# member line requires ≥1 modifier** and the return-type slot refuses `=`. That keeps
  `if (`/`foreach (` out of the index and makes `static readonly Regex Rx = new Regex(...)` stay a
  field, not a method named `Regex`.
- **The member indent skips the loose brace under the type.** In C# the `{` of `class X` sits at the
  *type's* indent; adopting it as the member indent found zero members.
- **A nested type is indexed but does not reset the member indent** — resetting it made every member
  of the outer type declared after it disappear.
- **`case "literal":` is indexed at any depth**, with no indent gate: in a CLI the verb table is the
  real search target (71 verbs in tia's `Program.cs`). Numeric/enum cases stay out.
- **`git ls-files --others --ignored --exclude-standard --directory`, not `git check-ignore`** —
  one call per run instead of thousands of processes. `--others` by construction never lists a
  tracked file, so a versioned file that matches an ignore rule stays indexed.
- **`core.quotePath=false` is mandatory** — without it a folder with an accent comes back
  octal-escaped (`\303\247`) and the prefix never matches. Found by testing against a PT-BR folder.
- **Rejected: putting `proj`/`workspace` in `SKIP_DIRS`.** Names too generic to ban in a global tool;
  the right rule is the repo's `.gitignore`.
- **Rejected: raising the 24-symbol preview cap** of `write_map`. The header at the top of the file
  already carries the whole list, which is the skill's 2-read design.

## Next steps (ordered)
1. Run it on another real C# repo (one with `record`, `partial class` and a file-scoped namespace)
   and see if the member indent holds — only the `namespace { class { … } }` layout was exercised.
2. `evals/evals.json` got no C# nor `.gitignore` case; `test_navindex.py` covers both.
3. If a large, dirty repo shows up, measure the cost of `git ls-files` (assumed negligible today).

## Key files
- `scripts/navindex.py` — the NAV INDEX header at the top has each symbol's line; `git_ignored`,
  `walk`, `symbols` are the touched points.
- `scripts/test_navindex.py` — the `CS` sample + the `.gitignore` test in a `tempfile` with `git init`.
- `references/internals.md` — per-language rules (section **C#**) and the section **Gitignored paths**.
- `__navi__.md` / `scripts/__navi__.md` — the repo's own maps, regenerated.

## Open / blockers
- **Multi-line signatures are still out** (declared ceiling with a `ponytail:` comment), same as the
  JS and Python branches.
- **Plain C# fields are not indexed** on purpose (only methods, constructors and properties). If a
  repo depends on a public constant, that is a new rule, not a bug.
- **`--include-ignored` has no dedicated test** — the opposite path (no filter) is the tested one.
- Repos whose maps already covered a gitignored folder will **shrink** on the first regeneration
  after this release. That is the goal, but it surprises whoever did not read the CHANGELOG (in tia
  the tree dropped from 263 files/44 folders to 84/10).

## Skills
- navindex

## Effort
**Low** for step 1 — run the script on a repo and read the map; the yardstick already exists
(`test_navindex.py` + `internals.md`). Raise to **medium** if the new layout (file-scoped
namespace, one-line `record`) requires touching the member indent, which is the fragile part of the
extraction. Reasoning is not the bottleneck: the cost is finding a C# repo with a different layout.
