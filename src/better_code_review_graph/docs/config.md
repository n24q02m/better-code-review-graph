# config Tool Documentation

Server configuration, status, and cache management.

## Actions

### status
Show current server status including graph path, node/edge counts, embedding backend, and last update time.

**Parameters:**
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "status"}
```

**Returns:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "graph_path": "/path/to/.code-review-graph/graph.db",
  "embedding_backend": "local",
  "total_nodes": 1234,
  "total_edges": 5678,
  "files_count": 42,
  "languages": ["Python", "TypeScript"],
  "embeddings_count": 890,
  "last_updated": "2026-03-20T12:00:00"
}
```

---

### set
Update a runtime setting.

**Parameters:**
- `key` (required): Setting key
- `value` (required): New value

**Valid keys:**
- `log_level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)

**Example:**
```json
{"action": "set", "key": "log_level", "value": "DEBUG"}
```

---

### cache_clear
Remove all computed embeddings from the graph database. After clearing, run `graph action=embed` to recompute.

**Parameters:**
- `repo_root`: Repository root path (auto-detected)

**Example:**
```json
{"action": "cache_clear"}
```

**Returns:**
```json
{
  "status": "cache cleared",
  "embeddings_removed": 890
}
```
