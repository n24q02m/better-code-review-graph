import sys

filepath = "src/better_code_review_graph/embeddings.py"
with open(filepath) as f:
    lines = f.readlines()

start_line = -1
end_line = -1
for i, line in enumerate(lines):
    if "def embed_nodes(" in line:
        start_line = i
    if start_line != -1 and "return len(to_embed)" in line:
        end_line = i + 1
        break

if start_line != -1 and end_line != -1:
    new_func = """    def embed_nodes(self, nodes: list[GraphNode], batch_size: int = 64) -> int:
        \"\"\"Compute and store embeddings for a list of nodes.

        Skips File nodes and nodes whose text + provider haven't changed.
        \"\"\"
        if not self.backend:
            return 0

        provider_name = self._get_backend_name()

        # Batch fetch existing metadata to avoid N+1 queries
        qualified_names = [n.qualified_name for n in nodes if n.kind != "File"]
        existing_meta = {}
        if qualified_names:
            batch_sz = 450
            for i in range(0, len(qualified_names), batch_sz):
                batch = qualified_names[i : i + batch_sz]
                rows = self._conn.execute(
                    "SELECT qualified_name, text_hash, provider FROM embeddings WHERE qualified_name IN (SELECT value FROM json_each(?))",
                    (json.dumps(batch),),
                ).fetchall()
                for r in rows:
                    existing_meta[r["qualified_name"]] = (r["text_hash"], r["provider"])

        # Filter to nodes that need embedding
        to_embed: list[tuple[GraphNode, str, str]] = []

        for node in nodes:
            if node.kind == "File":
                continue
            text = _node_to_text(node)
            text_hash = hashlib.sha256(text.encode()).hexdigest()

            existing = existing_meta.get(node.qualified_name)

            if (
                existing
                and existing[0] == text_hash
                and existing[1] == provider_name
            ):
                continue
            to_embed.append((node, text, text_hash))

        if not to_embed:
            return 0

        # Encode in batches
        texts = [t for _, t, _ in to_embed]
        vectors = self.backend.embed_texts(texts, dimensions=_DEFAULT_DIMS)

        for (node, _text, text_hash), vec in zip(to_embed, vectors, strict=True):
            blob = _encode_vector(vec)
            self._conn.execute(
                \"\"\"INSERT OR REPLACE INTO embeddings
                   (qualified_name, vector, text_hash, provider)
                   VALUES (?, ?, ?, ?)\"\"\",
                (node.qualified_name, blob, text_hash, provider_name),
            )

        self._conn.commit()
        return len(to_embed)
"""
    lines[start_line:end_line] = [new_func]
    with open(filepath, "w") as f:
        f.writelines(lines)
    print("Successfully patched embed_nodes")
else:
    print(f"Could not find embed_nodes: {start_line}, {end_line}")
    sys.exit(1)
