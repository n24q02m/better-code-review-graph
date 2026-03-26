## 2024-05-19 - N+1 Query Bottleneck Resolution
**Learning:** SQLite iteration in deeply nested structure mapping (e.g. `get_impact_radius` and query patterns like `callees_of` and `children_of`) triggers N+1 query bottlenecks that add large amounts of execution time overhead.
**Action:** Always batch node-lookups and edge-lookups in GraphStore by constructing batch queries with `IN` clauses up to SQLite variable limit threshold (e.g. batch size 450) and map them dynamically over list collections.
