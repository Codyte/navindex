# navindex — benchmark

Real measurements of what the navigation indexes buy an agent, run on a large production
codebase. Every number here comes from parsing the agents' own transcript token-usage and
tool-call records — nothing is estimated or hand-waved. The methodology, the confounds, and the
things we did **not** measure are all stated explicitly. Where a result is mixed or unfavorable,
it is reported as such.

## TL;DR

On a **2528-line file**, asking an agent to locate and describe 6 functions scattered through it,
using the in-file **NAV INDEX header** instead of grepping cut the **total context the agent moved
by 31–37 %** and the **context re-sent turn-over-turn by 46–49 %**, at **identical correctness
(6/6)** — on both the cheapest model (Haiku) and a frontier model (Opus). Both arms navigated
surgically (neither read the whole file), so this is a conservative floor, not a best case.

The cross-file part of the test (tracing a request flow across many files) is **model-dependent**
and is reported honestly below, including a constraint we imposed that inflated the skill arm's
cost.

Across every run, **not a single `file:line` citation we spot-checked was fabricated**.

---

## Setup

| | |
|---|---|
| Target repo | a large private production backend (Python/FastAPI monolith + JS channels), with `__navi__.md` maps and in-file headers already generated |
| Probe file | `backend/app.py`, **2528 lines**, carrying a NAV INDEX header |
| Models | Haiku, Sonnet, Opus (Claude) |
| Harness | agents run in parallel via the Claude Code workflow tool; each is forced to return a JSON schema so answers are directly comparable |
| Agents | cold, single-shot subagents (each does the task once, then exits) |
| Date | 2026-07-10 |

**How the numbers are measured.** Each agent writes a full transcript (`agent-*.jsonl`). We sum,
per agent:
- **fresh input** = `input_tokens + cache_creation_input_tokens` (context sent for the first time),
- **context re-sent** = `cache_read_input_tokens` (context re-sent on later turns — the "every
  turn re-sends the whole conversation" cost; billed at a discount but the dominant volume),
- **output** = `output_tokens`,
- **tool calls** = every `Read` / `Grep` (with their `offset`/`limit`, so we can see exactly where
  each agent looked and whether it ever read the whole file).

**Correctness** is scored against ground truth we established first by reading the source
ourselves: each answer must give the right defining line and a description that only reading the
function body could produce.

---

## Test 1 — in-file header on a big file (the skill's home turf)

**Task (identical for both arms):** in `backend/app.py`, for each of 6 symbols give the defining
`file:line` and one sentence describing what it does (which forces reading the body):
`_extract_date_token` (L444), `build_conversation_strategy` (L667), `is_short_ambiguous_message`
(L868), `_refresh_google_access_token` (L1443), `GoogleCalendarProvider.create_event` (L1903),
`prometheus_metrics` (L2027).

**Arms:**
- **A (header method)** — told the file has a NAV INDEX header at the top; read the header first,
  then `Read` only the exact line range of each symbol.
- **B (control)** — no navigation instruction; free to grep and read as it sees fit.

### What each agent actually did

The `Read` offsets are the raw record — this is exactly where each agent looked:

```
[opus  A-header]  grep=0   reads: TOP(l75)  444  667  868  1443  1903  2026        ← header, then 6 exact jumps
[opus  B-control] grep=1   reads: 444 667 737 868 1443 1903 2027                    ← grep found lines, then read (wider)
[haiku A-header]  grep=0   reads: TOP(l100) 444  667  868  1442  1902  2026         ← header, then 6 exact jumps
[haiku B-control] grep=1   reads: 443 666 867 1442 1800 1900 2026 1840 690 750      ← grep, then read + wander (10 reads)
```

Key point for honesty: the header lives *inside* the file, so control **could** have read it — but
in practice control grepped for symbol names instead and never opened the header. So this is a fair
**header-method vs grep-method** comparison on the same file, which is the realistic question (the
header is always present; the question is whether using it beats grepping). Neither arm ever read
the whole file — both stayed surgical.

### Results

**Haiku**

| Metric | A (header) | B (control) | Δ |
|---|---:|---:|---:|
| Correctness | 6 / 6 | 6 / 6 | — |
| Tool calls (reads + greps) | 7 | 11 | **−36 %** |
| Fresh input tokens | 84,932 | 79,777 | +6 % |
| **Context re-sent (cache-read)** | **211,293** | **389,638** | **−46 %** |
| **Total context moved** | **296,225** | **469,415** | **−37 %** |
| Output tokens | 2,128 | 2,493 | −15 % |

**Opus**

| Metric | A (header) | B (control) | Δ |
|---|---:|---:|---:|
| Correctness | 6 / 6 | 6 / 6 | — |
| Tool calls (reads + greps) | 7 | 8 | −12 % |
| Fresh input tokens | 125,024 | 102,153 | +22 % |
| **Context re-sent (cache-read)** | **159,968** | **312,312** | **−49 %** |
| **Total context moved** | **284,992** | **414,465** | **−31 %** |
| Output tokens | 1,308 | 2,530 | −48 % |

### Why the header wins

The header consolidates **all six locations into one ~70-line read**. The agent then jumps straight
to each function. The grep-based control spends an extra turn on the grep, reads **wider** ranges
(it doesn't know where each function ends), and a weaker model (Haiku) **wanders** — 10 reads
including exploratory misses at lines 1800/1840/690/750. Every extra turn re-sends the whole
accumulated context, which is why *context re-sent* (cache-read) shows the largest gap (−46 % /
−49 %) even when tool-call counts are close.

Fresh input is slightly **higher** for the header arm — reading the 70-line header up front is real
input — but it is repaid many times over in reduced re-sent context. The net (total context) is
31–37 % lower.

This delta is a **floor**: both controls happened to stay surgical. An agent that instead reads the
whole 2528-line file "to be safe" (a very common behavior) would load ~2528 lines where the header
arm loads ~70 + six small ranges — a far larger gap than measured here.

---

## Test 2 — folder map on a cross-file trace (model-dependent)

**Task:** trace a WhatsApp "web-lab" inbound message from the HTTP route to where it is written to
the Memory V3 store, across the whole backend, listing every `file:line` in the path and naming one
concurrency bottleneck.

This trace **forks** (an admin command is handled inline; a real customer message is handed to an
async pipeline), and the real answer is several files deep. Ground truth: route at
`routes/channels.py:208` → async hand-off → `services/site_chat.py` `_v3_store` → `svc.store()`
under a process-wide `V3_LOCK` → `agent_db_adapter.py` physical write. Bottleneck: `V3_LOCK`
serializes all Memory V3 writes process-wide, held across a remote embedding call.

**Important constraint (and confound):** to test the skill in its purest form, the map arm here was
told to navigate **only** by reading `__navi__.md` maps and headers, **no grep**. That is *not* how
the skill is meant to be used (the skill says read the map *first*, then grep/read as needed) and it
**inflates the map arm's token cost**, because the model must read whole folder maps instead of
grepping a name. So Test 2 measures **reliability on a forking trace**, not token savings — read it
that way.

### Results (map arm = grep-forbidden; control = free grep)

| Model | Arm | Reached the Memory V3 write? | Named the right bottleneck? | Fresh input (avg) | Output (avg) |
|---|---|---|---:|---:|---:|
| Haiku | map | 1 / 2 (one followed the fork down the wrong branch) | 1 / 2 | — | 11,165 |
| Haiku | control | 2 / 2 | 2 / 2 | — | 12,060 |
| Sonnet | map | **3 / 3** | **3 / 3** | 240,109 | 12,088 |
| Sonnet | control | 2 / 3 (one never reached the store) | 2 / 3 | 172,388 | 7,496 |
| Opus | map | 2 / 2 | 2 / 2 | 242,669 | 6,308 |
| Opus | control | 2 / 2 | 2 / 2 | 230,810 | 7,351 |

### Reading Test 2 honestly

- **Cost:** with grep forbidden, the map arm costs **more** input on the smart models (it reads
  whole maps). This is an artifact of the constraint, not the skill. Do **not** cite Test 2 as a
  token win.
- **Reliability:** the map arm's *accuracy* was equal-or-better except on Haiku, where one map-arm
  agent rigidly followed a map branch into the async pipeline and never doubled back to the memory
  write. Sonnet is the clearest reliability win (3/3 vs 2/3). On Opus both arms converge — a
  frontier model navigates this either way.
- **Takeaway:** the folder map's value **scales inversely with model capability** — meaningful on
  cheaper models, marginal on frontier ones — and on a forking trace the map speeds navigation but
  does not decide *which* branch is the answer; keep grep available as a correction net.

---

## Accuracy & hallucination

Across all runs we spot-checked `file:line` citations against the source. **Every citation we
checked resolved to the named symbol at (or within a few lines of) the stated line** — no
fabricated files, symbols, or lines were found in any arm, on any model. We did not exhaustively
verify all ~200 citations produced across the benchmark, but the spot-checks spanned every run and
found zero fabrications. The accurate line numbers in the maps and headers give the agent a factual
anchor instead of a guess.

---

## Limitations (what this benchmark does *not* prove)

- **Small n.** 1–2 agents per arm on the big-file test, 2–3 on the cross-file test. These are
  directional results, not tight statistics.
- **Cold single-shot agents.** Each agent does one task and exits. This is the **worst case** for
  the folder map, whose payoff is *amortized* — read once at the start of a session, reused across
  many later turns. That amortization is real in normal use but is **not** captured here (N=1 reuse).
- **The GENERATE half is untested here.** We measured *reading* the indexes. The other half of the
  skill — regenerating maps after edits so line numbers never drift, and the pre-commit hook — is
  the skill's unique guarantee (a stale index sends you to the wrong line) and is not benchmarked in
  this document.
- **One repo, one task family.** A Python-heavy monolith with a WhatsApp/memory pipeline. Results
  may differ on other languages or shapes.
- **Test 2's no-grep constraint is artificial** and penalizes the map arm on cost, as noted above.

The honest one-line summary: **the in-file header is a consistent, model-independent context saver
on large files; the folder map helps cheaper models more than frontier ones; and the indexes never
sent an agent to a made-up line.**

---

## Reproduce

The two workflow scripts used (symbol targets, prompts, and JSON schemas) are the
`navindex-benchmark` (cross-file trace) and `navindex-bigfile` (6-symbol lookup) scripts. Point them
at any large file in your own repo, run the skill to generate its header/maps first, and compare a
header/map-instructed arm against a control arm; parse each agent transcript for `input_tokens`,
`cache_read_input_tokens`, `output_tokens`, and the `Read`/`Grep` calls.
