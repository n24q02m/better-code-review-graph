import time

import networkx as nx


def bfs_original(nxg, seeds, max_depth, max_nodes, repo_qns):
    visited = set()
    frontier = seeds.copy()
    depth = 0
    impacted = set()
    truncated = False

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
        if len(visited) + len(next_frontier) > max_nodes:
            truncated = True
            break
        frontier = next_frontier
        depth += 1
    return impacted, truncated


def bfs_optimized(nxg, seeds, max_depth, max_nodes, repo_qns):
    visited = set()
    frontier = seeds.copy()
    depth = 0
    impacted = set()
    truncated = False

    while frontier and depth < max_depth:
        next_frontier = set()
        for qn in frontier:
            visited.add(qn)
            # Use intersection rather than checking if each is in repo_qns
            if qn in nxg:
                # Get the set of valid neighbors
                neighbors = set(nxg.neighbors(qn))
                if repo_qns is not None:
                    neighbors &= repo_qns
                neighbors -= visited
                next_frontier.update(neighbors)
                impacted.update(neighbors)
            if qn in nxg:
                preds = set(nxg.predecessors(qn))
                if repo_qns is not None:
                    preds &= repo_qns
                preds -= visited
                next_frontier.update(preds)
                impacted.update(preds)
        if len(visited) + len(next_frontier) > max_nodes:
            truncated = True
            break
        frontier = next_frontier
        depth += 1
    return impacted, truncated


nxg = nx.gnp_random_graph(5000, 0.05, directed=True)
nxg = nx.DiGraph(nxg)
seeds = set(list(nxg.nodes)[:5])
repo_qns = set(list(nxg.nodes)[:2500])

start = time.time()
for _ in range(100):
    impact1, t1 = bfs_original(nxg, seeds, 3, 50000, repo_qns)
t_orig = time.time() - start

start = time.time()
for _ in range(100):
    impact2, t2 = bfs_optimized(nxg, seeds, 3, 50000, repo_qns)
t_opt = time.time() - start

print(f"Original: {t_orig:.4f}s")
print(f"Optimized: {t_opt:.4f}s")
print(f"Matches: {impact1 == impact2}")
