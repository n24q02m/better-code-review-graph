## 2026-03-28 - Precalculate query norm in semantic search
**Learning:** In the SQLite graph store backend, brute-force cosine similarity scans re-calculated the query vector's `math.hypot` norm once for every single row fetched from the database, scaling redundantly with graph size.
**Action:** Always precalculate query-level invariants outside of database fetch loops. Modify similarity functions (`_cosine_similarity`) to optionally accept precomputed norms to skip expensive recalculation in hot loops.
