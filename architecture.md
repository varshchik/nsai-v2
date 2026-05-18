# Architecture v2

Compact English overview. Full version (Russian): [principles_ru.md](./principles_ru.md).

NSAI v2 is a word co-occurrence graph with connection classification by sentence-level contexts. The principle behind every decision: **connections live between words, not at a word.** A word has no global metric (degree, frequency, importance); it is an entry point for traversal.

## Base cycle

Signal → split into sentence-contexts → record immediate co-occurrences with ctx_id attribution → query → path search → classification by context intersection.

The graph mutates only from an external signal through `add()`. Queries (`paths`, `classify`, `explain`) are read-only. No inference is written back into the graph; everything is recomputed on each query.

## What is stored

Three structures, nothing more:

- `adj[a][b]` — co-occurrence count for the pair (bidirectional).
- `contexts[ctx_id]` — original sentence text.
- `edge_ctx[(a,b)]` — set of ctx_ids where the pair appeared. Inverted index, needed for O(path length) classification.

No fact types, no roles, no tags. Words are symbols, contexts are sentence ids, edges are pairs of adjacent positions.

## Base operation

`of(w)` — the neighbors of a word. Everything else is composition over `of`:

- "neighbors of neighbors": `{k for n in of(w) for k in of(n)} - {w}`
- a path of length N: BFS / DFS repeatedly calling `of`
- intersection of neighborhoods: `set(of(a)) & set(of(b))`

There is no separate "depth" concept; there is a parameter `max_w` — how far to expand the search. Every word along the path participates in the analysis equally.

## Connection classification

A connection between two words is discovered through a path in the graph. Each path is classified:

- **Assertion** — length 1 (direct co-occurrence) OR all edges of the path share a ctx_id. The system can point to the specific source text.
- **Reasoning** — edges of the path come from different contexts. Between adjacent edges there is a **context junction node** — a word through which the route switches contexts.

The distinction is purely structural: intersection of `ctx_id` sets of adjacent edges. No thresholds, no heuristics, no training.

When several alternative paths classify as reasoning, the diversity of junction nodes is analyzed:
- the same node across all paths → weak association through a single word;
- different nodes across many paths → stable indirect connection.

## Example: "Did Plato live in Greece?"

Corpus (Russian):
```
В Греции живет философ Сократ.            ← ctx0  (Socrates lives in Greece)
Философ Аристотель в Греции.              ← ctx1  (Philosopher Aristotle in Greece)
Философ Платон живет в Афинах.            ← ctx2  (Plato lives in Athens)
Аристотель родился в Греции.              ← ctx4  (Aristotle was born in Greece)
```

No direct statement "Plato lived in Greece" exists in any ctx. The graph finds several paths:

- `платон → живет → греции` via junction `живет` (edge `платон↔живет` in ctx2, edge `живет↔греции` in ctx0)
- `платон → философ → аристотель → в → греции` via junctions `философ`, `в`
- `платон → живет → в → греции` via `живет`, `в`

All paths are reasoning. Junction nodes: `живет`, `философ`, `в` — three different ones. The system marks the connection as "stable indirect": a route to the conclusion exists, but no direct fact does. This is an **honest** answer — not "yes", not "no", but "derivable through context switch, never stated directly".

Compare with "Did Plato live in Athens?" — an assertion is found with a direct reference to ctx2.

## Pair strength is not word weight

`adj[a][b] = N` is stored but does not enter classification. It is a local structural fact about a pair, not a global metric of a word. Path bottleneck strength (min of edge strengths) is a diagnostic, not a classification criterion.

No matter how many times the pair `платон↔ученик` is repeated, the edge `ученик↔гулял` (seen once in another context) does not form an assertion "плato walked". The structural fact about context separation outweighs the quantitative fact about repetitions.

## System boundary

At width 1 (direct co-occurrence) the graph **does not distinguish direction or subject change**. "Cat eats fish" and "Fish eats cat" produce identical neighborhoods.

This is an architectural specialization, not a bug. Distinguishing roles requires syntactic parsing and brings us back to v1. The trade is accepted in exchange for:

- language independence;
- working with arbitrary sequences (text, events, actions, notes);
- explainability via direct ctx reference;
- ~170 lines of code with no external dependencies.

## Discovery, not verification

The graph reports found connections with their classification; it does not deliver a verdict of truth. To a query "P?" the system shows: "here are corpus assertions about P", or "here are derivations through context change", or "no connection in the data". The user interprets which confidence mode applies.

Truth is determined by input and consistency with it. The system does not claim to know more than it has been shown.

**Conflict is not a system operation.** If the corpus contains "Plato lived in Athens" and "Plato lived in Sparta", the system finds both assertions and shows both, without choosing. Conflict is the user's observation over the system output, not a background scanner. Same principle as v0.1.

## Universality

The graph does not know what is fed into it. The same code works on:

- text in any language (no morphological analyzer);
- parallel bilingual texts (translation as co-occurrence in a shared ctx);
- event sequences and action logs;
- any formal sequences of symbols.

Boundary: in inflected languages, morphological forms of one word are different nodes. If this matters, an external clustering module is added without changing the core.

## Relation to v1

v1 (NSAI v0.1) is a symbolic architecture with typed facts `(predicate, [participants])` extracted by the natasha UD parser. v1 distinguishes roles and direction; it requires linguistic expertise for each new language.

v2 does not distinguish roles. v2 works on any language without preparation.

These two systems solve different problems. v1 — for structured fact extraction. v2 — for discovery of neighbor connections with direct explainability. Both remain valid in the repository.

## Status

Draft v0.2. Implementation file `neighbors.py`, no external dependencies. Recorded optimization directions (persistence, streaming ingest, vocab/int ids) are engineering, not architectural changes. Semantics of operations is preserved across them.

System boundary (above) is not a "deficiency to be removed" but a property of the architecture. If a task requires distinguishing roles and direction — that is a task for v1 (or for a system that types the input before feeding it into v2), not for v2.
