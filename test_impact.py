def original():
    visited = set()
    frontier = {"A", "B"}
    nxg = {"A": ["B", "C"], "B": ["C", "D"], "C": [], "D": []}

    class N:
        def __contains__(self, k):
            return k in nxg

        def neighbors(self, k):
            return nxg[k]

        def predecessors(self, k):
            return []

    g = N()
    next_frontier = set()
    for qn in sorted(list(frontier)):  # Force order A then B
        visited.add(qn)
        for neighbor in g.neighbors(qn):
            if neighbor in visited:
                continue
            next_frontier.add(neighbor)
    return next_frontier, visited


def optimized():
    visited = set()
    frontier = {"A", "B"}
    nxg = {"A": ["B", "C"], "B": ["C", "D"], "C": [], "D": []}

    class N:
        def __contains__(self, k):
            return k in nxg

        def neighbors(self, k):
            return nxg[k]

        def predecessors(self, k):
            return []

    g = N()
    visited.update(frontier)
    next_frontier = set()
    for qn in sorted(list(frontier)):
        for neighbor in g.neighbors(qn):
            if neighbor in visited:
                continue
            next_frontier.add(neighbor)
    return next_frontier, visited


print("Original:", original())
print("Optimized:", optimized())
