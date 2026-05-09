"""Cross-repo symbol resolvers (Phase 2).

Per-language modules live alongside this package marker. Task 8 will
add a language dispatcher; for now callers should import the language
resolver directly, e.g.::

    from better_code_review_graph.resolver.python import PythonResolver
"""
