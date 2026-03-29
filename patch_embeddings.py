with open("src/better_code_review_graph/embeddings.py") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if (
        "query_vec = self.backend.embed_single_query(query, dimensions=_DEFAULT_DIMS)"
        in line
    ):
        lines[i - 1] = "            from typing import Any, cast\n"
        lines[i] = (
            "            query_vec = cast(Any, self.backend).embed_single_query(query, dimensions=_DEFAULT_DIMS)\n"
        )

with open("src/better_code_review_graph/embeddings.py", "w") as f:
    f.writelines(lines)
