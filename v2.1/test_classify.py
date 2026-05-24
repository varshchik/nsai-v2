"""Unit tests for classify() sliding-window algorithm.

Covers cases reviewer specifically requested:
- length-2 path
- length-3 path with different sources
- path where window exists in one source but not another
- path with position loops (multiple edge occurrences in window)
- empty path
- path shorter than minimum
"""

from neighbors_v2_1 import Graph


def assert_eq(actual, expected, label):
    status = '✓' if actual == expected else '✗'
    print(f'  {status} {label}: got {actual!r}, expected {expected!r}')
    return actual == expected


def test_empty_path():
    print('\n[1] empty path')
    g = Graph()
    g.add('a b c')
    r = g.classify([])
    assert_eq(r['kind'], 'none', 'empty list → none')

    r = g.classify(['a'])
    assert_eq(r['kind'], 'none', 'single-node → none')


def test_length_2():
    print('\n[2] length-2 path (direct edge)')
    g = Graph()
    g.add('кот спит')
    r = g.classify(['кот', 'спит'])
    assert_eq(r['kind'], 'утверждение', 'direct adjacency → assertion')
    # Note: for len-2 paths, anchor window is computed and returned even
    # though kind is determined unconditionally (len(path)==2 short-circuits).
    # This gives consistent provenance for all paths.
    assert r['anchor_window'] is not None, 'anchor window provided for citation'
    print('  ✓ anchor_window provided for citation')


def test_length_3_same_source():
    print('\n[3] length-3 path, single source, fits window')
    g = Graph()
    g.add('кот спит на диване')  # positions: кот=0 спит=1 на=2 диване=3
    r = g.classify(['кот', 'спит', 'на'], width=2)
    assert_eq(r['kind'], 'утверждение', 'tight path within width=2')


def test_length_3_different_sources():
    print('\n[4] length-3 path, edges from different sources')
    g = Graph()
    g.add('кот спит', source='s1')      # edge (кот,спит) in s1
    g.add('спит ночью', source='s2')    # edge (спит,ночью) in s2
    r = g.classify(['кот', 'спит', 'ночью'], width=10)
    assert_eq(r['kind'], 'рассуждение',
              'no source contains all edges → reasoning')


def test_window_in_one_source_not_another():
    print('\n[5] same edge in two sources, fits in one only')
    g = Graph()
    g.add('кот спит. кот ест', source='s1')      # кот-ест far from кот-спит in s1
    g.add('кот спит ест', source='s2')           # кот-спит, спит-ест tight in s2
    r = g.classify(['кот', 'спит', 'ест'], width=2)
    assert_eq(r['kind'], 'утверждение',
              'fits tight in s2 → assertion')


def test_position_loops():
    print('\n[6] path with multiple occurrences (sliding window picks optimum)')
    # Reviewer's failure case for old greedy:
    # A=[10], B=[0, 25], C=[20], width=19
    # Greedy: B=0 (closest to A=10), then C=20 → span 0..20 = 20 > 19 FAIL
    # Optimal: B=25, C=20 → span 10..25 = 15 ≤ 19 PASS
    g = Graph()
    # Manually construct the edge positions to test the algorithm
    g.edge_positions[g._edge_key('a', 'b')] = [('s', 10)]
    g.edge_positions[g._edge_key('b', 'c')] = [('s', 0), ('s', 25)]
    g.edge_positions[g._edge_key('c', 'd')] = [('s', 20)]
    g.adj['a']['b'] = 1; g.adj['b']['a'] = 1
    g.adj['b']['c'] = 2; g.adj['c']['b'] = 2
    g.adj['c']['d'] = 1; g.adj['d']['c'] = 1
    g.sources['s'] = [''] * 30  # dummy fill

    r = g.classify(['a', 'b', 'c', 'd'], width=19)
    assert_eq(r['kind'], 'утверждение',
              'sliding window finds non-greedy solution')

    # Anchor window should be [10, 20, 25] (span=15)
    if r['anchor_window']:
        _, positions = r['anchor_window']
        assert_eq(max(positions) - min(positions), 15,
                  'minimal span = 15 (not the greedy 20)')


def test_window_exceeded():
    print('\n[7] path span exceeds width → reasoning')
    g = Graph()
    g.add('a b c d e f g h')  # a=0, b=1, ..., h=7
    r = g.classify(['a', 'b', 'c', 'd', 'e'], width=2)
    assert_eq(r['kind'], 'рассуждение',
              'span 4 > width 2 → reasoning')


def test_repeated_edge_in_one_source():
    print('\n[8] repeated edge has multiple position candidates')
    g = Graph()
    g.add('кот спит кот спит кот')
    # (кот, спит) edge has positions: 0, 1, 2, 3 (overlapping window pairs)
    r = g.classify(['кот', 'спит'], width=1)
    assert_eq(r['kind'], 'утверждение', 'short path always assertion if path exists')

    # Multi-edge case where some edges have multiple positions
    g2 = Graph()
    g2.add('a b a b c')
    # (a,b) positions: 0, 1, 2  (a-b, b-a, a-b)
    # (b,c) positions: 3
    r = g2.classify(['a', 'b', 'c'], width=2)
    assert_eq(r['kind'], 'утверждение',
              'algorithm picks (a,b)=2 with (b,c)=3, span=1')


def run_all():
    tests = [
        test_empty_path,
        test_length_2,
        test_length_3_same_source,
        test_length_3_different_sources,
        test_window_in_one_source_not_another,
        test_position_loops,
        test_window_exceeded,
        test_repeated_edge_in_one_source,
    ]
    for t in tests:
        t()
    print('\n--- done ---')


if __name__ == '__main__':
    run_all()
