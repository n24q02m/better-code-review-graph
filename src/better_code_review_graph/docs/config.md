# config Tool Documentation

Server configuration, status, cache management, and credential setup.

## Config Actions

### status
Show current server status including graph counts and the selected embedding
backend, model, fixed storage dimensions, and fallback result. Status resolves
configuration only; it does not load the embedding model.

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
  "embedding_model": "n24q02m/Qwen3-Embedding-0.6B-ONNX",
  "embedding_dimensions": 768,
  "embedding_fallback": "none",
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

---

## Setup Actions

### setup_status
Show current credential state and relay setup URL (if any).

**Example:**
```json
{"action": "setup_status"}
```

---

### setup_start
Start relay setup session to configure API keys via browser.

**Parameters:**
- `force`: If true, reconfigure even when already configured (default: false)

**Example:**
```json
{"action": "setup_start"}
```

---

### setup_skip
Set local mode permanently — relay will not trigger on next restart.

**Example:**
```json
{"action": "setup_skip"}
```

---

### setup_reset
Clear saved credentials and reset to awaiting_setup state.

**Example:**
```json
{"action": "setup_reset"}
```

---

### setup_complete
Re-resolve credentials from current environment variables (picks up manually set API keys).

**Example:**
```json
{"action": "setup_complete"}
```
