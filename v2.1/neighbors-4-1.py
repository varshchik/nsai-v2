"""NSAI v2.1 — Co-occurrence graph with positional provenance, pure stream.

Differences from v2:

1. ctx primitive removed. Instead of storing sentences by ctx_id, edges
   store occurrence positions as (source, index) tuples. Context proximity
   is computed as "positions fit within a window of given width in the
   same source".

2. width became a query-time parameter. Previously it was implicitly
   sentence-bounded via ctx partitioning. Now any width can be specified
   per query:
       - narrow (1-3): tight local associations
       - medium (5-10): cross-sentence reasoning
       - wide (50+): broad associative discovery

3. Provenance: source[start..end] instead of ctx_id. Direct reference
   to original text.

4. Character n-gram morphological similarity (Jaccard). Emergent
   morphology without lemmatizer — works on a single-sentence corpus.

5. Pure stream adjacency. Punctuation is NOT treated as a structural
   boundary — it's a writing convention, not a feature of language
   (live dialogue has no periods). Adjacency flows through the entire
   token stream regardless of punctuation. Fact isolation is achieved
   via source decomposition: separate add() calls or distinct sources.

All tunable defaults are exposed as module-level constants at the top.
"""

from collections import defaultdict, Counter
from pathlib import Path
from typing import Literal, Optional
import heapq
import re


# ── default parameters ─────────────────────────────────────────────────
# Change here, applies module-wide. Each can be overridden per-call via
# explicit method parameter.

DEFAULT_WIDTH = 6              # window for assertion-vs-reasoning classification
                               # narrow (1-3): tight, local associations
                               # medium (5-10): cross-sentence
                               # wide   (50+): broad associative

DEFAULT_MAX_PATH_LEN = 5       # max path length in DFS search
DEFAULT_MAX_PATHS = 20         # max paths to find per query

NGRAM_SIZE = 3                 # character n-gram size for morphology
MORPH_THRESHOLD = 0.5          # minimum similarity for morph_neighbors

SOURCE_DEFAULT = "default"     # source name when add() called without one
SECTION_DELIMITER = "[end]"    # section separator in load_file


# ── type aliases ───────────────────────────────────────────────────────

PathKind = Literal['утверждение', 'рассуждение', 'none']
# Semantic labels are user-facing (from the published article).
# Literal gives type safety without runtime enum overhead.


class Graph:

    def __init__(self, default_width: int = DEFAULT_WIDTH):
        self.adj: dict[str, Counter] = defaultdict(Counter)
        self.edge_positions: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
        self.sources: dict[str, list[str]] = {}
        # Inverted n-gram index for morph_neighbors: ngram -> set of words.
        # Built incrementally in add() to avoid rescanning self.adj.
        self._ngram_index: dict[str, set[str]] = defaultdict(set)
        # Track which words have already been indexed so _index_word is
        # O(1) on repeats. Without this, _ngrams() is recomputed for every
        # token occurrence — wasteful on natural text where most tokens
        # are repeats of the same vocabulary.
        self._indexed: set[str] = set()
        self.default_width = default_width

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return re.findall(r'\w+', text.lower())

    def _edge_key(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if a <= b else (b, a)

    def _index_word(self, word: str) -> None:
        """Add word to inverted n-gram index for morph_neighbors lookup.

        Idempotent: re-indexing the same word is a no-op (early return),
        so the per-token loop in add() can call this freely without
        recomputing n-grams for repeated tokens.
        """
        if word in self._indexed:
            return
        self._indexed.add(word)
        for ng in self._ngrams(word, NGRAM_SIZE):
            self._ngram_index[ng].add(word)

    def add(self, text: str, source: str = SOURCE_DEFAULT) -> None:
        """Ingest text. Pure stream adjacency — no sentence boundaries.
        Punctuation is ignored (writing artifact, not language feature).
        Fact isolation: use separate sources / add() calls.
        """
        if source not in self.sources:
            self.sources[source] = []
        tokens = self.tokenize(text)
        if not tokens:
            return
        if len(tokens) < 2:
            self.sources[source].extend(tokens)
            self._index_word(tokens[0])
            return
        base_pos = len(self.sources[source])
        self.sources[source].extend(tokens)
        for tok in tokens:
            self._index_word(tok)
        for i, (a, b) in enumerate(zip(tokens, tokens[1:])):
            self.adj[a][b] += 1
            self.adj[b][a] += 1
            key = self._edge_key(a, b)
            self.edge_positions[key].append((source, base_pos + i))

    def load_file(self, path: str,
                  delimiter: str = SECTION_DELIMITER,
                  source_prefix: Optional[str] = None) -> None:
        """Load .txt file with sectioned content.

        Each section between delimiter becomes its own source — gives
        atomic-fact isolation when testing with a single file.
        Source naming: '<filename>:<idx>' by default.
        """
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        base = source_prefix or Path(path).stem
        sections = [s.strip() for s in content.split(delimiter) if s.strip()]
        for i, section in enumerate(sections):
            self.add(section, source=f"{base}:{i}")

    def load_files(self, *paths: str,
                   delimiter: str = SECTION_DELIMITER) -> None:
        """Load multiple .txt files. Each file gets independent source-namespace."""
        for path in paths:
            self.load_file(path, delimiter=delimiter)

    def load_dir(self, directory: str,
                 pattern: str = "*.txt",
                 delimiter: str = SECTION_DELIMITER) -> None:
        """Load all files from directory matching glob pattern."""
        for path in sorted(Path(directory).glob(pattern)):
            self.load_file(str(path), delimiter=delimiter)

    def of(self, word: str) -> Counter:
        return self.adj.get(word.lower(), Counter())

    def positions_of_edge(self, a: str, b: str) -> list[tuple[str, int]]:
        return self.edge_positions.get(self._edge_key(a.lower(), b.lower()), [])

    # ── path navigation ──────────────────────────────────────────────
    def paths(self, a: str, b: str,
              max_w: int = DEFAULT_MAX_PATH_LEN,
              max_paths: int = DEFAULT_MAX_PATHS) -> list[list[str]]:
        """Find paths between two nodes.

        Priority: (1) shorter path, (2) lower total inverse-weight cost
        (stronger co-occurrence = shorter effective distance).
        Heap orders directly by (length, cost, seq) — final order matches
        heap pop order, no re-sort needed.
        """
        a, b = a.lower(), b.lower()
        if a not in self.adj or b not in self.adj or a == b:
            return []

        # heap entries: (path_length, cost, seq, path_list, visited_set)
        # seq for deterministic tie-breaking, visited as O(1) lookup set
        seq = 0
        heap: list = [(0, 0.0, seq, [a], {a})]
        results: list[list[str]] = []

        while heap and len(results) < max_paths:
            length, cost, _, path, visited = heapq.heappop(heap)
            current = path[-1]
            if current == b and len(path) >= 2:
                results.append(path)
                continue
            if length >= max_w:
                continue
            # sorted() makes iteration order independent of dict-insertion
            # history, so reloading the same corpus in a different order
            # yields identical path enumeration. Without this, tie-broken
            # results drift with insertion order.
            for nb, weight in sorted(self.adj[current].items()):
                if nb in visited:
                    continue
                seq += 1
                new_visited = visited | {nb}
                new_cost = cost + (1.0 / weight)
                heapq.heappush(heap, (length + 1, new_cost, seq,
                                      path + [nb], new_visited))
        return results

    def _find_window(self, positions_per_edge: list,
                     src: str, width: int) -> Optional[list[int]]:
        """Sliding window over sorted positions: find minimum-span subset
        containing one position per edge, with span <= width.
        Returns sorted positions used, or None if no fit possible."""
        n_edges = len(positions_per_edge)
        items = sorted(
            (p, ei) for ei, edge_pos in enumerate(positions_per_edge)
            for (s, p) in edge_pos if s == src
        )
        if len(set(ei for _, ei in items)) < n_edges:
            return None

        edge_count = [0] * n_edges
        covered = 0
        left = 0
        best: Optional[tuple[int, list[int]]] = None  # (span, positions)

        for right in range(len(items)):
            pos_r, edge_r = items[right]
            if edge_count[edge_r] == 0:
                covered += 1
            edge_count[edge_r] += 1

            while covered == n_edges:
                pos_l, _ = items[left]
                span = pos_r - pos_l
                if span <= width and (best is None or span < best[0]):
                    seen: dict[int, int] = {}
                    for j in range(left, right + 1):
                        p, ei = items[j]
                        seen.setdefault(ei, p)
                    best = (span, sorted(seen.values()))

                left_edge = items[left][1]
                edge_count[left_edge] -= 1
                if edge_count[left_edge] == 0:
                    covered -= 1
                left += 1

        return best[1] if best else None

    def classify(self, path: list[str], width: Optional[int] = None) -> dict:
        """Check window-fit for a co-occurrence path.

        Computes whether path's edges have positions covering a single
        source-window of given width (via sliding-window minimum cover).

        Returns dict with structural assessment:
          kind            — semantic label (PathKind)
          path            — input path
          edges           — list of edge keys
          edge_strengths  — co-occurrence counts per edge
          bottleneck      — min edge strength along path
          anchor_window   — (source, positions) of covering window if found
          junction_nodes  — nodes where adjacent edges do not come from
                            physically contiguous positions in any single
                            source (i.e. context-switch points; independent
                            of width)
          width_used      — width parameter applied
        """
        if not path or len(path) < 2:
            return {'kind': 'none', 'path': path, 'edges': [], 'edge_strengths': [],
                    'bottleneck': 0, 'anchor_window': None,
                    'junction_nodes': [], 'width_used': width or self.default_width}
        if width is None:
            width = self.default_width

        edges = [self._edge_key(a, b) for a, b in zip(path, path[1:])]
        positions_per_edge = [self.edge_positions[e] for e in edges]

        anchor_window = None
        for src in self.sources:
            positions = self._find_window(positions_per_edge, src, width)
            if positions:
                anchor_window = (src, positions)
                break

        # Junction detection: two consecutive edges in the path come from
        # the same physical adjacency in a source iff their stored positions
        # differ by exactly 1 (each edge stores the position of its left
        # token, so a pair stream "...x y z..." records (x,y) at p and
        # (y,z) at p+1). Width is not used here — width governs the
        # global reasoning-window fit, while junctions are about literal
        # contiguity in the source stream.
        junctions = []
        for i in range(len(edges) - 1):
            fit = False
            for src in self.sources:
                pos_i = [p for (s, p) in positions_per_edge[i] if s == src]
                pos_j = {p for (s, p) in positions_per_edge[i+1] if s == src}
                if any((pi + 1) in pos_j or (pi - 1) in pos_j for pi in pos_i):
                    fit = True
                    break
            if not fit:
                junctions.append(path[i+1])

        strengths = [self.adj[a][b] for a, b in zip(path, path[1:])]
        kind: PathKind = 'утверждение' if (len(path) == 2 or anchor_window) else 'рассуждение'
        return {
            'kind': kind,
            'path': path,
            'edges': edges,
            'edge_strengths': strengths,
            'bottleneck': min(strengths),
            'anchor_window': anchor_window,
            'junction_nodes': junctions,
            'width_used': width,
        }

    def cite(self, source: str, positions: list[int]) -> str:
        """Return text fragment from source covering given positions (+1 right)."""
        tokens = self.sources.get(source, [])
        if not positions:
            return ''
        s = max(0, min(positions))
        e = min(len(tokens), max(positions) + 2)
        return ' '.join(tokens[s:e])

    # ── morphological similarity ─────────────────────────────────────
    @staticmethod
    def _ngrams(word: str, n: int = NGRAM_SIZE) -> set[str]:
        """Character n-grams with boundary padding (^ start, $ end).

        Padding makes prefix and suffix n-grams structurally distinct
        from internal ones (so "сократ" and "акрост" don't accidentally
        match through a shared "кра") and ensures short words (len < n)
        still produce a useful overlap signature instead of degenerating
        to the whole word.
        """
        padded = f"^{word}$"
        if len(padded) < n:
            return {padded}
        return {padded[i:i+n] for i in range(len(padded) - n + 1)}

    def morph_similarity(self, w1: str, w2: str, n: int = NGRAM_SIZE) -> float:
        """Character n-gram Jaccard similarity. No lemmatizer needed.
        With boundary padding: 'сократ' vs 'сократа' ≈ 0.63,
        'сократ' vs 'платон' = 0.00."""
        g1, g2 = self._ngrams(w1.lower(), n), self._ngrams(w2.lower(), n)
        if not (g1 and g2):
            return 0.0
        return len(g1 & g2) / len(g1 | g2)

    def morph_neighbors(self, word: str,
                        threshold: float = MORPH_THRESHOLD,
                        n: int = NGRAM_SIZE) -> list[tuple[str, float]]:
        """Find words in graph with similar character composition.

        Uses inverted n-gram index — only scans candidates sharing at least
        one n-gram with the query. O(|ngrams(w)| * |candidates|) instead
        of O(|V|).
        """
        word = word.lower()
        query_ngrams = self._ngrams(word, n)
        # Collect candidates via inverted index
        candidates: set[str] = set()
        for ng in query_ngrams:
            candidates.update(self._ngram_index.get(ng, ()))
        candidates.discard(word)

        result = []
        for w in candidates:
            sim = self.morph_similarity(word, w, n)
            if sim >= threshold:
                result.append((w, sim))
        result.sort(key=lambda x: -x[1])
        return result

    # ── analysis and formatting ──────────────────────────────────────
    def analyze(self, a: str, b: str,
                max_w: int = DEFAULT_MAX_PATH_LEN,
                max_paths: int = DEFAULT_MAX_PATHS,
                width: Optional[int] = None) -> dict:
        """Pure analysis. Returns structured data, no I/O.

        Result fields:
          a, b      — query nodes
          width     — applied width
          paths     — list of classify() dicts for each found path
          assertions, reasonings — partitioned lists by kind
        """
        if width is None:
            width = self.default_width
        ps = self.paths(a, b, max_w=max_w, max_paths=max_paths)
        classified = [self.classify(p, width=width) for p in ps]
        return {
            'a': a, 'b': b,
            'width': width,
            'max_w': max_w,
            'paths': classified,
            'assertions': [c for c in classified if c['kind'] == 'утверждение'],
            'reasonings': [c for c in classified if c['kind'] == 'рассуждение'],
        }

    def format_analysis(self, analysis: dict) -> str:
        """Format analysis dict as human-readable text."""
        a, b = analysis['a'], analysis['b']
        width = analysis['width']
        paths = analysis['paths']

        if not paths:
            return f"{a} ↔ {b}: связи в радиусе {analysis['max_w']} нет"

        lines = []
        assertions = analysis['assertions']
        reasonings = analysis['reasonings']

        if assertions:
            header = (f"{a} ↔ {b}: УТВЕРЖДЕНИЕ ({len(assertions)} путь(ей), "
                      f"width={width})")
            if reasonings:
                header += f" + {len(reasonings)} рассуждение(й)"
            lines.append(header)
        else:
            all_junctions = [j for c in reasonings for j in c['junction_nodes']]
            junction_freq = Counter(all_junctions)
            unique_j = len(junction_freq)
            lines.append(f"{a} ↔ {b}: РАССУЖДЕНИЕ ({len(reasonings)} путь(ей), "
                         f"{unique_j} разных узлов смены, width={width})")
            if unique_j == 1:
                only = next(iter(junction_freq))
                lines.append(f"  ⚠ все пути проходят через одно слово «{only}» — слабая связь")
            elif unique_j >= 3:
                tops = junction_freq.most_common(3)
                lines.append("  устойчивая косвенная связь: смены через "
                             + ", ".join(f"«{w}»×{n}" for w, n in tops))

        for c in paths:
            tag = '✓' if c['kind'] == 'утверждение' else '~'
            lines.append(f"  {tag} [{c['kind']}, прочность={c['bottleneck']}] "
                         f"{' → '.join(c['path'])}")
            if c['anchor_window']:
                src, positions = c['anchor_window']
                quote = self.cite(src, positions)
                pos_str = f"{min(positions)}..{max(positions)+1}"
                lines.append(f"      {src}[{pos_str}]: «{quote}»")
            elif c['junction_nodes']:
                lines.append(f"      смены через: {', '.join(c['junction_nodes'])}")

        return '\n'.join(lines)

    def explain(self, a: str, b: str,
                max_w: int = DEFAULT_MAX_PATH_LEN,
                max_paths: int = DEFAULT_MAX_PATHS,
                width: Optional[int] = None) -> None:
        """Print human-readable analysis (convenience wrapper)."""
        print(self.format_analysis(
            self.analyze(a, b, max_w=max_w, max_paths=max_paths, width=width)))
