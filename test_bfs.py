import random
import time


# Generate dummy graph
class DummyGraph:
    def __init__(self, n, m):
        self.adj = {i: [] for i in range(n)}
        self.rev = {i: [] for i in range(n)}
        for _ in range(m):
            u, v = random.randint(0, n - 1), random.randint(0, n - 1)
            self.adj[u].append(v)
            self.rev[v].append(u)

    def __contains__(self, n):
        return n in self.adj

    def neighbors(self, n):
        return self.adj[n]

    def predecessors(self, n):
        return self.rev[n]


nxg = DummyGraph(10000, 50000)
frontier = set(random.sample(range(10000), 500))


def original(nxg, frontier_init, max_depth=3, repo_qns=None):
    visited = set()
    frontier = frontier_init.copy()
    depth = 0
    impacted = set()

    start = time.time()
    while frontier and depth < max_depth:
        next_frontier = set()
        for qn in frontier:
            visited.add(qn)
            if qn in nxg:
                for neighbor in nxg.neighbors(qn):
                    if neighbor in visited:
                        continue
                    if repo_qns is not None and neighbor not in repo_qns:
                        continue
                    next_frontier.add(neighbor)
                    impacted.add(neighbor)
            if qn in nxg:
                for pred in nxg.predecessors(qn):
                    if pred in visited:
                        continue
                    if repo_qns is not None and pred not in repo_qns:
                        continue
                    next_frontier.add(pred)
                    impacted.add(pred)
        frontier = next_frontier
        depth += 1
    return time.time() - start


def optimized(nxg, frontier_init, max_depth=3, repo_qns=None):
    visited = set()
    frontier = frontier_init.copy()
    depth = 0
    impacted = set()

    start = time.time()
    while frontier and depth < max_depth:
        visited.update(frontier)
        next_frontier = set()
        for qn in frontier:
            if qn in nxg:
                for neighbor in nxg.neighbors(qn):
                    if neighbor not in visited and (
                        repo_qns is None or neighbor in repo_qns
                    ):
                        next_frontier.add(neighbor)
                        impacted.add(neighbor)
                for pred in nxg.predecessors(qn):
                    if pred not in visited and (repo_qns is None or pred in repo_qns):
                        next_frontier.add(pred)
                        impacted.add(pred)
        frontier = next_frontier
        depth += 1
    return time.time() - start


t1 = sum(original(nxg, frontier) for _ in range(100))
t2 = sum(optimized(nxg, frontier) for _ in range(100))
print(f"Original: {t1:.4f}s")
print(f"Optimized: {t2:.4f}s")
