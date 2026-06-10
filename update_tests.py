with open("tests/test_bare_suffix_correctness.py") as f:
    content = f.read()

# Update test_inheritors_of_no_bare_fallback
content = content.replace(
    "test_inheritors_of_no_bare_fallback", "test_inheritors_of_finds_bare_suffix"
)
content = content.replace(
    "# It should NOT find b.py::Sub because we disabled fallback.",
    "# It SHOULD find b.py::Sub via bare-suffix matching.",
)
content = content.replace(
    "results, edges_out)", 'None, "a.py::Base", results, edges_out)'
)
content = content.replace("assert len(results) == 0", "assert len(results) == 1")
content = content.replace("assert len(edges_out) == 0", "assert len(edges_out) == 1")

# Update test_tests_for_no_bare_fallback
content = content.replace(
    "test_tests_for_no_bare_fallback", "test_tests_for_finds_bare_suffix"
)
content = content.replace("assert len(results) == 0", "assert len(results) == 1")

# Update test_importers_of_no_bare_fallback
content = content.replace(
    "test_importers_of_no_bare_fallback", "test_importers_of_finds_bare_suffix"
)
content = content.replace(
    "results, edges_out)", 'None, "app/a.py", results, edges_out)'
)
content = content.replace("assert len(results) == 0", "assert len(results) == 1")

with open("tests/test_bare_suffix_correctness.py", "w") as f:
    f.write(content)
