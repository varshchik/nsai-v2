# NSAI v2

**Word co-occurrence graph with context-tracked path classification.** Independent research, draft v0.2.

NSAI v2 builds a graph of immediate word co-occurrences from text and tracks which sentence each edge came from. When asked whether two words are connected, the system finds paths through the graph and classifies them: **assertion** — all edges of a path live in a common context (the connection is stated directly in some sentence), **reasoning** — edges cross sentence boundaries (a chain assembled from independent sources). No dependency parsing, no POS tags, no lemmatization. Any language, any sequence of symbols.

## What this is

- Discrete observation storage from text — no compression into weights, no training.
- Built-in explainability: any answer can point to the specific corpus sentences it came from.
- Single-author research project continuing v0.1, rewritten from scratch after reformulating the task.

## What this is not

- Not a language parser. The graph knows nothing about morphology, syntax, or roles.
- Not a statement verifier. The graph cannot distinguish "Cat eats fish" from "Fish eats cat" at width 1 (see system boundary below).
- Not an LLM replacement. It solves a different problem: connection discovery with direct source attribution.

## Architecture in one paragraph

Text is split into sentences; each sentence is a separate context. For each pair of immediate neighbors within a sentence, an edge is recorded in `adj[a][b]` (bidirectionally) and indexed in an inverted table `edge_ctx[(a,b)] → {ctx_ids}`. The single base operation is `of(w)` — the neighbors of a word. On top of it, `paths(a, b, max_w)` finds all simple paths up to a bounded length (DFS with backtracking). Each path is classified by intersecting the context sets of its edges: if a common ctx exists — **assertion**; otherwise — **reasoning**, with the nodes where context changes flagged as junction nodes. Pair strength (co-occurrence count) is stored but **does not enter classification**: it is informative for display, but should not change connection type. A word as an object has no global metric (degree, weight, frequency) — this is a deliberate architectural choice, see [principles_ru.md](./principles_ru.md) for details.

Full architecture: [principles_ru.md](./principles_ru.md) (Russian, detailed) · English summary: [architecture.md](./architecture.md)

Russian-language docs: [README_ru.md](./README_ru.md) · [architecture_ru.md](./architecture_ru.md)

## Installation

Python 3.10+. No external dependencies.

```bash
git clone https://github.com/varshchik/nsai
cd nsai/v2
python neighbors.py
```

## Quick example

```python
from neighbors import Graph

g = Graph()
g.add("В Греции живет философ Сократ.")
g.add("Философ Аристотель в Греции.")
g.add("Философ Платон живет в Афинах.")

g.explain("сократ", "философ")
# сократ ↔ философ: УТВЕРЖДЕНИЕ (1 путь)
#   ✓ [утверждение, прочность=1] сократ → философ
#       ctx0: «В Греции живет философ Сократ»

g.explain("платон", "греции")
# платон ↔ греции: РАССУЖДЕНИЕ (5 путей, 3 разных узлов смены)
#   устойчивая косвенная связь: смены через «философ»×3, «живет»×2, «в»×2
#   ~ [рассуждение, прочность=1] платон → живет → греции
#       смены через: живет
#   ...
```

"Plato in Greece" was **never stated directly**, but multiple routes converge to that connection via different junctions — this is a stable indirect association, flagged as reasoning, not as fact.

The example is in Russian because that is the working corpus; the code itself is language-agnostic.

## License

AGPL-3.0. Any improvements remain open.

## Relation to v1

v1 (NSAI v0.1) lives in [v1/](../v1/) — a symbolic architecture with dependency-tree parsing (natasha + pymorphy3) that extracts typed facts `(predicate, [participants])`. v1 and v2 solve different problems: v1 — structured fact extraction with roles, v2 — connection discovery via co-occurrences without typing. Both architectures remain valid for their respective formulations.
