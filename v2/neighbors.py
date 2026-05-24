"""Граф соседств с контекстами.

Хранилище:
    adj[a][b] = сколько раз a и b были соседями  (как раньше)
    contexts:  ctx_id -> исходный текст контекста
    ctx_edges: ctx_id -> множество пар (a,b) которые возникли в этом контексте
    edge_ctx:  (a,b) -> множество ctx_id где встречалась пара  (обратный индекс)

Контекст = одно предложение (разделители: .?! и переводы строк).

Это даёт различать:
    утверждение  — все рёбра пути живут в общем контексте → "так и сказано"
    рассуждение  — рёбра живут в разных контекстах        → "склейка через разные источники"
"""

from collections import defaultdict, deque, Counter
import re


class Graph:
    _SENT_SPLIT = re.compile(r'[.!?]+|\n+')

    def __init__(self):
        self.adj: dict[str, Counter] = defaultdict(Counter)
        self.contexts: dict[int, str] = {}
        self.ctx_edges: dict[int, set[tuple[str, str]]] = defaultdict(set)
        self.edge_ctx: dict[tuple[str, str], set[int]] = defaultdict(set)
        self._next_ctx = 0

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return re.findall(r'\w+', text.lower())

    def _edge_key(self, a: str, b: str) -> tuple[str, str]:
        """Каноничный ключ для неориентированного ребра."""
        return (a, b) if a <= b else (b, a)

    def add(self, text: str) -> None:
        """Разбиваем на предложения, каждое — отдельный контекст."""
        for sent in self._SENT_SPLIT.split(text):
            sent = sent.strip()
            if not sent:
                continue
            tokens = self.tokenize(sent)
            if len(tokens) < 2:
                continue
            ctx_id = self._next_ctx
            self._next_ctx += 1
            self.contexts[ctx_id] = sent
            for a, b in zip(tokens, tokens[1:]):
                self.adj[a][b] += 1
                self.adj[b][a] += 1
                key = self._edge_key(a, b)
                self.ctx_edges[ctx_id].add(key)
                self.edge_ctx[key].add(ctx_id)

    # ── базовая операция ──────────────────────────────────────────────
    def of(self, word: str) -> Counter:
        return self.adj.get(word.lower(), Counter())

    def contexts_of_edge(self, a: str, b: str) -> set[int]:
        return self.edge_ctx.get(self._edge_key(a.lower(), b.lower()), set())

    # ── навигация: пути ──────────────────────────────────────────────
    def paths(self, a: str, b: str, max_w: int = 5, max_paths: int = 20) -> list[list[str]]:
        """Все простые пути a → b длины <= max_w. Без повторов узлов внутри пути."""
        a, b = a.lower(), b.lower()
        if a not in self.adj or b not in self.adj or a == b:
            return []
        results: list[list[str]] = []
        path = [a]
        visited = {a}
        def dfs(cur: str) -> None:
            if len(results) >= max_paths or len(path) > max_w:
                return
            for nb in self.of(cur):
                if nb == b:
                    results.append(path + [b])
                    if len(results) >= max_paths:
                        return
                elif nb not in visited:
                    visited.add(nb)
                    path.append(nb)
                    dfs(nb)
                    path.pop()
                    visited.remove(nb)
        dfs(a)
        results.sort(key=len)
        return results

    def classify(self, path: list[str]) -> dict:
        """Классификация одного пути."""
        if not path or len(path) < 2:
            return {'kind': 'none'}
        edges = list(zip(path, path[1:]))
        edge_ctxs = [self.contexts_of_edge(a, b) for a, b in edges]
        common = set.intersection(*edge_ctxs) if edge_ctxs else set()
        junctions = []
        for i in range(len(edges) - 1):
            if not (edge_ctxs[i] & edge_ctxs[i + 1]):
                junctions.append(path[i + 1])  # сам узел смены
        strengths = [self.adj[a][b] for a, b in edges]
        kind = 'утверждение' if (len(path) == 2 or common) else 'рассуждение'
        return {
            'kind': kind,
            'path': path,
            'edges': edges,
            'edge_strengths': strengths,
            'bottleneck': min(strengths),    # слабейшее звено = прочность пути
            'common_contexts': sorted(common),
            'junction_nodes': junctions,     # узлы где меняется контекст
        }

    def explain(self, a: str, b: str, max_w: int = 5, max_paths: int = 20) -> None:
        """Полный отчёт: все пути, классификация, агрегат по узлам смены."""
        ps = self.paths(a, b, max_w=max_w, max_paths=max_paths)
        if not ps:
            print(f"{a} ↔ {b}: связи в радиусе {max_w} нет")
            return

        classified = [self.classify(p) for p in ps]
        assertions = [c for c in classified if c['kind'] == 'утверждение']
        reasonings = [c for c in classified if c['kind'] == 'рассуждение']

        # Заголовок: что главное про эту пару?
        if assertions:
            print(f"{a} ↔ {b}: УТВЕРЖДЕНИЕ ({len(assertions)} путь(ей))"
                  + (f" + {len(reasonings)} рассуждение(й)" if reasonings else ""))
        else:
            # Все пути — рассуждения. Анализируем junction'ы.
            all_junctions = [j for c in reasonings for j in c['junction_nodes']]
            junction_freq = Counter(all_junctions)
            unique_j = len(junction_freq)
            print(f"{a} ↔ {b}: РАССУЖДЕНИЕ ({len(reasonings)} путь(ей), "
                  f"{unique_j} разных узлов смены)")
            if unique_j == 1:
                only = next(iter(junction_freq))
                print(f"  ⚠ все пути проходят через одно слово «{only}» — "
                      f"слабая ассоциация")
            elif unique_j >= 3:
                tops = junction_freq.most_common(3)
                print(f"  устойчивая косвенная связь: смены через "
                      + ", ".join(f"«{w}»×{n}" for w, n in tops))

        # Детали каждого пути
        for i, c in enumerate(classified, 1):
            tag = '✓' if c['kind'] == 'утверждение' else '~'
            print(f"  {tag} [{c['kind']}, прочность={c['bottleneck']}] "
                  f"{' → '.join(c['path'])}")
            if c['common_contexts']:
                for cid in c['common_contexts']:
                    print(f"      ctx{cid}: «{self.contexts[cid]}»")
            elif c['junction_nodes']:
                print(f"      смены через: {', '.join(c['junction_nodes'])}")


# ── демо ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    g = Graph()
    # Базовый набор
    g.add("В Греции живет философ Сократ.")
    g.add("Философ Аристотель в Греции.")
    g.add("Философ Платон живет в Афинах.")
    g.add("Платон учитель Аристотеля.")
    # Добавим повторы и альтернативные опоры
    g.add("Аристотель родился в Греции.")
    g.add("Платон обучал Аристотеля философии.")
    g.add("Сократ учил Платона.")

    print("=== контексты ===")
    for cid, txt in g.contexts.items():
        print(f"  ctx{cid}: «{txt}»")
    print()

    for a, b in [("сократ", "философ"),
                 ("платон", "афинах"),
                 ("платон", "греции"),
                 ("сократ", "аристотель"),
                 ("сократ", "греции")]:
        g.explain(a, b, max_w=4, max_paths=15)
        print()
