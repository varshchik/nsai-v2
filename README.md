# NSAI v2.1

**Word co-occurrence graph with positional provenance and query-time window classification.** Independent research, working refactor of v2.

NSAI builds a graph of immediate word co-occurrences from text and tracks the position of each occurrence in its source. When asked whether two words are connected, the system finds paths through the graph and classifies them by **window-fit**: **assertion** — there exists a source-window of given width covering all edges of the path (the connection appears localized in some passage), **reasoning** — no such window exists (chain assembled from positions too far apart). No dependency parsing, no POS tags, no lemmatization, no sentence boundaries.

> **Explainability is structural, not post-hoc.** Every answer points to a specific positional span of the source from which it was derived. There is no internal state hiding the logic — the graph and the answer are made of the same observations. This is a different kind of explainability than attention visualization or asking a black-box model to narrate its reasoning after the fact.

## What this is

- Discrete observation storage from text — no compression into weights, no training.
- Single-author research project, working refactor of v2 (see [CHANGES.md](./CHANGES.md)).

## What this is not

- Not a language parser. The graph knows nothing about morphology, syntax, or roles.
- Not a statement verifier. The graph cannot distinguish "Cat eats fish" from "Fish eats cat" at width 1.
- Not an LLM replacement. It solves a different problem: connection discovery with direct source attribution.

## Architecture in one paragraph

Text is tokenized into a continuous stream — punctuation is ignored (a writing convention, not a feature of language; live dialogue has no periods). For each pair of immediate neighbors in the token stream, an edge is recorded in `adj[a][b]` (bidirectionally) and indexed by position in `edge_positions[(a,b)] → [(source, pos), ...]`. The single base operation is `of(w)` — the neighbors of a word. On top of it, `paths(a, b)` finds paths via weighted Dijkstra-like search (stronger co-occurrence ranks earlier). Each path is classified by checking whether a single source contains a window of given width covering all path edges (sliding-window minimum-cover algorithm). If yes — **assertion**, with the citation `source[start..end]`; otherwise — **reasoning**, with junction nodes where adjacent edges cannot fit width. Pair strength (co-occurrence count) is stored for display but **does not enter classification**. Width is a query-time parameter — narrow window = strict localization, wide window = broad association.

Full architecture: [principles_en.md](../principles_en.md) · changes from v2: [CHANGES.md](./CHANGES.md)

Russian-language docs: [README_ru.md](./README_ru.md) · [principles_ru.md](../principles_ru.md)

## Installation

Python 3.10+. No external dependencies.

```bash
git clone https://github.com/varshchik/nsai
cd nsai/v2.1
```

## Usage

### Run tests

```bash
python test_classify.py
# 23 passed, 0 failed

# Or with pytest if installed:
python -m pytest test_classify.py -v
```

### Quick example

```python
from neighbors import Graph

g = Graph()
g.add("В Греции живет философ Сократ.")
g.add("Философ Аристотель в Греции.")
g.add("Философ Платон живет в Афинах.")

g.explain("сократ", "философ")
# сократ ↔ философ: УТВЕРЖДЕНИЕ (1 путь, width=6)
#   ✓ [утверждение, прочность=1] сократ → философ
#       default[3..5]: «философ сократ философ»

g.explain("платон", "греции")
# платон ↔ греции: РАССУЖДЕНИЕ (5 путей, 3 разных узлов смены, width=6)
#   устойчивая косвенная связь: смены через «философ»×3, «живет»×2, «в»×2
#   ~ [рассуждение, прочность=1] платон → живет → греции
#       смены через: живет
```

"Plato in Greece" was **never stated directly**, but multiple routes converge on that connection via different junctions — a stable indirect association, flagged as reasoning, not as fact.

### Loading from files

```python
# Single file:
g.load_file('corpus.txt')

# With section delimiters for atomic-fact isolation
# (file content: "Сократ философ [end] Платон в Афинах")
g.load_file('atomic_facts.txt')
# creates sources atomic_facts:0, atomic_facts:1

# Multiple specific files:
g.load_files('socrates.txt', 'plato.txt', 'aristotle.txt')

# Whole directory:
g.load_dir('corpora/', pattern='*.txt')
```

Each file gets its own source-namespace via filename. Nodes merge across files (same word = one graph node), but positions stay isolated — cross-file paths classify as reasoning by definition.

### Query-time width

Width is set per query, not at graph build:

```python
g.explain("a", "b", width=2)   # tight, near-adjacent only
g.explain("a", "b", width=10)  # cross-sentence reasoning
g.explain("a", "b", width=50)  # broad association
```

### Structured analysis (for UI / further processing)

```python
analysis = g.analyze("сократ", "философ", width=3)
# returns dict: { paths, assertions, reasonings, width, ... }

# Format manually:
text = g.format_analysis(analysis)
```

`analyze()` returns pure structured data — easy to serialize to JSON, pass to a frontend, or process programmatically. `explain()` is a print-wrapper around `format_analysis(analyze(...))`.

### Morphological similarity (no lemmatizer)

```python
g.morph_similarity("сократ", "сократа")  # → 0.80
g.morph_neighbors("сократ", threshold=0.5)
# → [('сократа', 0.80), ('сократе', 0.80), ...]
```

Character n-gram Jaccard similarity. Inverted index built incrementally — O(|n-grams(w)| × |candidates|) lookup, not O(|V|) scan. Inspection tool only; not integrated into path-finding (preserves role distinction between morphological forms).

The example is in Russian because that is the working corpus; the code itself is language-agnostic.

## License

AGPL-3.0. Any improvements remain open.

## Contact

Issues, suggestions, or interesting use cases — open an issue, or write to [me@varshchik.dev](mailto:me@varshchik.dev).

## Relation to previous versions

- **v1** (NSAI v0.1) — [v1/](../v1/) — symbolic architecture with dependency-tree parsing (natasha + pymorphy3) extracting typed facts `(predicate, [participants])`. ~1500 lines.
- **v2** — [v2/](../v2/) — initial co-occurrence graph with sentence-based context. ~150 lines. Described in the [negation article](https://varshchik.dev/22052026_en.pdf).
- **v2.1** — this directory. Same conceptual approach as v2, with corrections (sliding-window classify, deterministic paths), engineering improvements (morphology, loaders, type safety), and a test suite. See [CHANGES.md](./CHANGES.md).

All architectures remain valid for their respective formulations.
