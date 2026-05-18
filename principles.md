*A word is an entry point for traversal, not an object with a metric. Connections live between words, not at a word.*

# 1. Core

One storage type, one base operation, three derived queries.

**Storage.** A co-occurrence graph: `adj[a][b] = N` means that words `a` and `b` were immediate neighbors in the text `N` times. The record is bidirectional: every observation `... a b ...` increments both `adj[a][b]` and `adj[b][a]`. Self-loops (`... 1 1 ...`) are normal and recorded without special rules.

In parallel, the system stores **contexts** — the original sentences of the corpus, each with a unique `ctx_id` — and an **inverted edge index** `edge_ctx[(a,b)] → {ctx_ids}`, recording in which contexts the pair appeared. Without the inverted index, classification would be O(number of contexts) per query; with it — O(path length).

**Base operation.** `of(w)` — the neighbors of word `w`. Returns a Counter `{neighbor → pair strength}`. This is everything the system can do with a single word. The system does not compute or use any global word characteristics (degree, frequency, importance).

**Queries are compositions of `of`.**

- `paths(a, b, max_w)` — all simple paths from `a` to `b` of length up to `max_w` steps. DFS with backtracking. Returns a list of paths sorted by length.
- `classify(path)` — the connection type for this path (see §2).
- `explain(a, b)` — aggregated report over all found paths, with per-path classification and analysis of junction nodes.

**What is NOT stored.** Word weights (degree, weight, frequency as a global metric). If a question of the form "how important is this word in general" arises about a word — it is not a question for the graph. The graph only knows what lies next to what, and in which sentence it was seen.

# 2. Assertion and reasoning

The graph distinguishes two modes of answering a "are A and B connected" query:

**Assertion** — a path of length 1 (direct co-occurrence), or a path of length >1 whose **edges all live in a common context**. That is, there exists a sentence in the corpus where this connection is stated. For such an answer, the system can **point to the source** — the specific ctx_id text from which the answer was derived. Explainability is direct, without interpretation.

**Reasoning** — a path of length >1 with no common context: the edges of the path come from different sentences. Between two adjacent edges of the path there is a **context junction node** — a word through which the route transitions from one context to another. This is not a corpus assertion but an inference made by the system from adjacent assertions.

The distinction is **fully structural**: it looks at the intersection of `ctx_id` sets of adjacent edges of the path. No POS tags, no "knowledge of roles", no thresholds. If edges shared a sentence — it is stated directly; if they did not — it is an assembled chain.

**Junction nodes are an observable property.** The word `философ` (`philosopher`) appears as a junction in the path "Platon → философ → Aristotle" because the edge `Platon↔философ` and the edge `философ↔Aristotle` never co-occur in the same sentence. In the corpus this means "Plato is a philosopher" and "Aristotle is a philosopher" are two **separate** assertions, and the transition between them through the shared node `философ` loses the subject. This is the structural analogue of the homonymy problem — without ontology, from text positions alone.

**Weak association vs stable indirect connection.** On a query with several alternative reasoning paths, two regimes are possible:
- all paths pass through the **same** junction node — this is one weak association through a single word (often a function word: a preposition, a copula);
- paths pass through **different** junction nodes — this is a stable indirect connection: several independent routes converge on a single conclusion.

The boundary between these regimes is continuous; in the current implementation, a connection is marked "stable" when it has ≥3 distinct junction nodes, but the threshold is an implementation parameter, not an architectural fact.

# 3. Pair strength is not word weight

The counter `adj[a][b] = N` is **pair strength**, not word weight. The distinction is fundamental:

- *Pair strength* is a structural fact about two specific words: "this pair is seen in the corpus N times". Local, relative.
- *Word weight* is a global characteristic of a single word: "word w is important / frequent / hub-like". Absolute.

Pair strength is used as an informative metric in reports, and as `bottleneck = min(edge strengths along path)` — a characterization of path durability. **Pair strength does not enter the assertion/reasoning classification.** No matter how many times "Plato is Aristotle's student" is repeated, this does not turn "Plato walked" via the edge "student→walked" into an assertion. The structural fact about context separation outweighs the quantitative fact about repetition.

Word weight is rejected as an architectural element. Earlier versions (v0.1, v3.x) tried to suppress function words through similar metrics; in every case it was a compensatory term masking a problem in the main formula. In v2 the function-word problem does not arise: function words are traversable through direct co-occurrences but do not accidentally cross the assertion/reasoning boundary, because classification looks at contexts rather than frequencies.

# 4. Discovery, not verification

The graph operates in a **connection discovery** mode, not in a **statement verification** mode.

The distinction is fundamental. Verification answers "is P true" and must have a falsification mechanism. Discovery answers "what does the corpus say about P" and shows the available evidence. The v2 graph is discovery: it reports the found paths with their classification but does not deliver a "true/false" verdict.

**Conflict is not a system operation.** If the corpus contains "Plato lived in Athens" and "Plato lived in Sparta", the system will find both assertions and show both, without choosing between them. Conflict is the user's observation over the system output, not a background scanner. Exactly the same principle as in v0.1.

**Truth is determined by input and consistency.** To the query "Is Socrates a philosopher?" the system does not assess truth universally — it checks consistency with the corpus it has been given. If the corpus says "Socrates is a philosopher" — assertion. If it does not, but the connection is derivable through context change — reasoning. If unreachable within `max_w` steps — there is no connection in the data.

This is an **honest** mode of operation: the system does not claim to know more than it has been shown.

# 5. System boundary

At width 1 (direct co-occurrence), the graph **does not distinguish the direction of a relation or a subject change**. "Cat eats fish" and "Fish eats cat" produce identical co-occurrences: `cat↔eats`, `eats↔fish`. At width 1 this is structurally indistinguishable without role typing.

**This is not a bug; it is an architectural specialization.** The solution "add roles via a UD parser" returns to v0.1, which did exactly that. v2 deliberately abandons roles in exchange for:

- language independence (any token sequence works);
- modality independence (texts, events, action sequences — anything);
- direct explainability via reference to ctx;
- minimal dependencies and code (~170 lines vs 1500 in v0.1).

The price is the inability to distinguish roles and direction on a single pair. The price is accepted.

Partial compensation for long queries: if the corpus contains enough repetitions with varying role orders, pair-strength statistics begin to highlight stable patterns. This is not role distinction in the strict sense, but an indirect signal. Whether to use it or not is an operator decision.

# 6. Emergent properties

Criterion: if attempting to formalize the property removes it, the property is emergent.

| Property | What produces it |
|---|---|
| Assertion / reasoning | Intersection of contexts of path edges |
| Context junction node | Adjacent edges with no common ctx |
| Weak association vs stable indirect connection | Diversity of junction nodes across alternative paths |
| Path durability | min of edge strengths along the route |
| Explainability | Direct ctx reference, no interpretation |
| Homonym distinction | Node `Z` in paths via different ctx — structurally different roles |
| Categorization | Many words sharing a junction node — membership in a common category |

None of these properties are programmed as separate modules. All arise from the bundle `(co-occurrence + context + inverted edge index)`.

# 7. Universality across content

The graph does not know what is fed into it. Input is a sequence of tokens with sentence-boundary markers. What those tokens *mean* is irrelevant.

A list of possible operating modes (the same code, different data):

- **Text in any language.** No morphological analyzer, no dictionaries. Works on slang, neologisms, typos, constructed languages. Boundary: in inflected languages, morphological forms of one word become separate nodes; statistics "scatter across buckets". This is not fixable without clustering (a separate module, not part of the core).

- **Parallel bilingual text.** `HELLO Привет. CAT Кошка.` — each pair becomes a context of two tokens. `hello↔привет` — assertion, a direct co-occurrence in a shared ctx. A bilingual dictionary emerges from co-occurrences without a translation module.

- **Event logs.** A sequence of user actions in an application (`login → open_inbox → reply → logout`) is processed as a "sentence" of actions. The query "are `login` and `reply` connected?" yields an assertion, a path of length 2. Behavior patterns are extracted as thematic co-occurrences.

- **Symbol sequences.** Numbers, musical notes, game moves, elements of any formal grammar. The graph does not verify logic; it accumulates observations.

This is not a "universal semantic model". It is a **tool for accumulating and navigating observations** regardless of what was observed.

# 8. Rejected solutions

Each item below was considered in the course of v2 development and rejected:

- **top-k words by number of connections, node degree as a metric.** This is word weight as a global object; it contradicts §3.
- **idf-like weights, specificity, frequency normalizations.** These metrics compensated for problems in counting in v3.x; in v2 the problem does not arise, and the metrics are not needed.
- **Depth as a separate concept distinct from width.** Every word along a path participates in the traversal; there is no distinction between "depth" and "width", only one parameter `max_w` — how far to expand the search.
- **Bidirectional BFS, k-shortest paths, priority by strong edges.** Premature optimization. On current corpora, plain DFS with length and count limits works; optimizations to be added when real pain arises, not preemptively.
- **Recording chains of length >1 when adding to the graph.** Connections `a↔c` via an intermediate `b` are discovered on query through `of(of(a))`, not baked in at ingest. Otherwise the storage bloats with transitive glue.
- **Pair strength as part of classification.** Strength affects display (bottleneck, path ranking) but does not change the connection type. An assertion remains an assertion regardless of edge strengths; a reasoning — a reasoning.
- **Contradiction as a system operation.** Conflict is an observation over the output, not a background scanner. Continuity with v0.1.
- **Morphological analyzer as part of the core.** Clustering of morphological forms is a separate module for languages where it is needed; not an architectural requirement.
- **Writing anything during a query.** `paths`, `classify`, `explain` are read-only. The graph mutates only from `add()` with an external signal.

# 9. Status

Draft v0.2. Implementation file `neighbors.py`, ~170 lines, no external dependencies. The architecture is stable at a level where further changes are weighed carefully against §8.

Recorded optimization directions (by need, not preemptively):

- **persistence** — saving the graph to disk so it doesn't have to be rebuilt on every run;
- **streaming ingest** — line-by-line reading of large corpora;
- **vocab + int ids** — replacing string keys with integer ids for memory efficiency.

All three are engineering, not architectural changes. The semantics of operations is preserved.

The system boundary (§5) is not "a defect to be eliminated" but a property of the architecture. If a task requires distinguishing roles and direction — that is a task for v1 (or for a system that types the input before feeding it into v2), not for v2.
