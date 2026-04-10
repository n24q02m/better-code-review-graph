import pytest
from tests.conftest import _make_node

def test_search_nodes_security_basics(tmp_graph_store):
    store = tmp_graph_store
    store.upsert_node(_make_node("login_service", "Function", "auth.py::login_service"))
    store.upsert_node(_make_node("LoginController", "Class", "auth.py::LoginController"))
    store.upsert_node(_make_node("process_data", "Function", "data.py::process_data"))
    store.commit()

    # Basic multi-word
    results = store.search_nodes("login service")
    assert len(results) == 1
    assert results[0].name == "login_service"

    # With kind filter
    results = store.search_nodes("login", kind="Class")
    assert len(results) == 1
    assert results[0].name == "LoginController"

    # No matches for non-existent kind
    results = store.search_nodes("login", kind="NonExistent")
    assert len(results) == 0

def test_search_nodes_sql_injection_attempt(tmp_graph_store):
    store = tmp_graph_store
    store.upsert_node(_make_node("normal_node", "Function", "test.py::normal_node"))
    store.commit()

    # Attempting to break out of the query
    injection_queries = [
        "' OR 1=1 --",
        "\") OR 1=1 --",
        "normal') OR '1'='1",
        "kind') OR 1=1 --",
    ]

    for q in injection_queries:
        results = store.search_nodes(q)
        assert len(results) == 0, f"Injection query '{q}' should return no results"

    # Attempting injection through kind
    results = store.search_nodes("normal", kind="Function' OR '1'='1")
    assert len(results) == 0
