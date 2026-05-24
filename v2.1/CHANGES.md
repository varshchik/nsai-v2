# Changes: v2 → v2.1

Status: working refactor, all tests passing.

## Architectural changes

### ctx as primitive removed
v2 stored sentences indexed by `ctx_id`; edges remembered which contexts
they appeared in. v2.1 replaces this with `(source, position)` tuples on
edges. Context proximity becomes "positions fit within a window of given
width in the same source".

Consequences:
- `width` becomes a query-time parameter (was implicitly sentence-bounded)
- Provenance: `source[start..end]` instead of `ctx_id` — direct reference
- Cross-sentence reasoning natural via wider window
- One mechanism (positions + window) replaces two (sentences + edge-ctx index)

### Pure stream adjacency
v2 used regex to split sentences before building adjacency; punctuation
acted as boundary between edges. v2.1 ignores punctuation entirely —
adjacency flows through the full token stream.

Justification: punctuation is a writing convention (Greek/Latin originally
had none, periods are 16th century print invention), not a feature of
language. Live dialogue has no periods. NSAI architectures meaning flow
in language, so writing artifacts shouldn't be structural primitives.

Fact isolation moved from implicit (author's punctuation) to explicit
(source decomposition via separate `add()` calls or `[end]` markers).

### Character-level morphological similarity
New: `morph_similarity()` and `morph_neighbors()` compute Jaccard
similarity over character n-grams. Closes a known weakness of v2 —
morphology via neighborhood distributions required large corpora.
Character-level structural similarity works on single-sentence corpora.

"сократ" vs "сократа" → 0.80 (without any lemmatizer)

Used as inspection tool only; not integrated into path-finding (preserves
role distinction between morphological forms — subject vs object stays
separated).

## Correctness fixes

### Sliding-window classify (was greedy)
v2 (and initial v2.1) used greedy nearest-position selection per edge,
which could miss valid windows. Counterexample (width=19):
- A=[10], B=[0, 25], C=[20]
- Greedy: B=0 (closest to anchor 10), then C=20 → span=20 > 19 → FAIL
- Correct: B=25, C=20 → span=15 ≤ 19 → assertion

v2.1 uses sliding-window algorithm over sorted positions, finding
minimum-span valid subset. Sees all valid configurations.

### Deterministic weighted paths
v2.1 initial version used DFS with `Counter` insertion-order traversal —
non-deterministic across runs. Now uses heap-based Dijkstra-like search
with priority `(path_length, inverse_weight_cost, sequence)`:
- Stronger co-occurrence → lower cost → ranked earlier
- Same-cost paths broken by sequence counter → deterministic
- Visited set tracked separately → O(1) cycle check

## Engineering improvements

### Performance
- Inverted n-gram index built in `add()` — `morph_neighbors` no longer
  scans all graph nodes. O(|ngrams(w)| × |candidates|) vs O(|V|).
- Visited set in `paths` traversal — O(1) cycle check vs O(len(path))
- Module-level `import heapq` instead of in-function

### API separation
`explain()` was monolithic print function. v2.1 splits into:
- `analyze(a, b)` — pure computation, returns structured dict
- `format_analysis(dict)` — presentation, returns string
- `explain(a, b)` — convenience wrapper: print(format(analyze(...)))

Programmatic users get structured data. UI integration trivial — JSON
serialize, return to frontend. Tests check analyze() without capturing
stdout.

### Type safety
`PathKind = Literal['утверждение', 'рассуждение', 'none']` instead of
bare strings. Compile-time check against typos. No runtime overhead.
Semantic labels themselves unchanged — they're user-facing choices from
the published article.

### Constants block
All tunable defaults exposed at module top: `DEFAULT_WIDTH`,
`DEFAULT_MAX_PATH_LEN`, `DEFAULT_MAX_PATHS`, `NGRAM_SIZE`,
`MORPH_THRESHOLD`, `SOURCE_DEFAULT`, `SECTION_DELIMITER`. No separate
config file — single point of tuning.

### Corpus loading
- `load_file(path)` — single .txt with optional `[end]` section separators
- `load_files(*paths)` — multiple files, each independent source namespace
- `load_dir(directory, pattern)` — glob-based directory loading

Each file becomes its own source namespace via filename stem. Nodes
merge across files (same word = one graph node), positions stay isolated
(cross-file paths classify as reasoning by definition).

### Documentation
Docstrings rewritten in English. Operation descriptions are structural
("checks window-fit for co-occurrence path"), not epistemic
("determines whether assertion holds"). User-facing labels in outputs
remain semantic (matches article terminology).

## Tests

v2 had no test suite — code correctness rested on demo runs.
v2.1 ships `test_classify.py` with 23 tests covering:

- `classify` sliding-window: empty path, length-2, length-3 same source,
  cross-source, window-fits-one-not-another, position-loops greedy
  failure case (regression test), window-exceeded, repeated edges
- `paths` weighted ranking: prefers strong edges, deterministic across
  calls, no self-loops, handles disconnected nodes, no node-revisits
- `morph_neighbors`: finds variants, threshold boundaries, incremental
  index updates, excludes query word, handles missing word
- `analyze`/`format_analysis`: structured-data smoke checks, no-paths
  case, assertion/reasoning text output

Tests use real `assert` statements; exit code 1 on failure. Compatible
with pytest without modification.

## Numbers

| Metric         | v2     | v2.1   |
|----------------|--------|--------|
| Lines (core)   | ~150   | 414    |
| Lines (tests)  | 0      | 288    |
| Methods        | 8      | 17     |
| Constants      | 0      | 7      |

Growth from ~150 → 414 is feature additions (loaders, morphology,
analysis split, type aliases) plus correctness work (sliding window,
weighted paths). Not bloat: each addition is justified by a specific
concern documented above.

## What didn't change

The architectural principle described in the negation article remains
unchanged:

- Nodes are words (no joining of "not_X")
- Edges are co-occurrence (no special edge types)
- Context membership through window-fit (no thresholds, no rules)
- Assertion vs reasoning via shared-window check
- Negation, identity, conflict, syllogism — all emergent, no primitives

v2.1 is the same idea under a cleaner mechanism. The article describes
v2 as it was at publication; v2.1 implements the same principle with
fewer artifacts (punctuation, ctx as primitive, sentence boundaries)
and stronger guarantees (correctness, determinism, type safety, tests).
