import re
import os

# We will only refactor `.fetchall()` in graph.py where it's safe and verified by test_graph_batch_fetch.py
# In tools.py we had test failures probably because of fetchall removals inside some tool methods where length or empty logic was used, or the list was re-used.

# Let's read tests output: `FAILED tests/test_server.py::TestReviewTool::test_review - TypeError: the JSON object must be str, bytes or bytearray, not list`
# This doesn't look related to `if not rows` in `tools.py` since it complains about list.

# But anyway, let's just restore original files and ONLY optimize the known batch fetch methods in graph.py which we tested perfectly.
