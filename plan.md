1. **Remove `.fetchall()` in `federation.py` and `embeddings.py`**
   - Update `_load_from_store` in `src/better_code_review_graph/federation.py` to iterate over the cursor directly instead of calling `.fetchall()`.
   - Update `_ensure_embeddings` in `src/better_code_review_graph/embeddings.py` to iterate over the cursor directly instead of calling `.fetchall()`.
   - This optimization reduces peak memory consumption by avoiding materialization of the intermediate result lists.

2. **Run tests to verify the optimization**
   - Run `uv run pytest tests/test_federation.py tests/test_embeddings.py` to make sure we didn't break any existing functionality.

3. **Complete pre-commit checks**
   - Ensure proper testing, verification, review, and reflection are done by following the pre-commit instructions.

4. **Submit PR**
   - Create a PR with the required Bolt format.
