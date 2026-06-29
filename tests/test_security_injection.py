import pytest
from unittest.mock import MagicMock, patch
from better_code_review_graph.temporal import TemporalIndex

def test_ensure_temporal_friendly_schema_rejects_malicious_type():
    """Verify that malicious column types are rejected."""
    mock_store = MagicMock()
    mock_conn = mock_store._conn

    # (cid, name, typ, notnull, dflt, pk)
    malicious_type = (0, "col1", "INT; DROP TABLE nodes; --", 0, None, 0)

    mock_conn.execute.side_effect = [
        MagicMock(fetchone=lambda: ("sqlite_autoindex_nodes_1",)),  # legacy check
        MagicMock(fetchall=lambda: [malicious_type]),  # PRAGMA table_info
    ]

    with pytest.raises(RuntimeError, match="Unsafe column type detected"):
        TemporalIndex(mock_store, current_sha="abc")

def test_ensure_temporal_friendly_schema_rejects_malicious_default():
    """Verify that malicious default values are rejected."""
    mock_store = MagicMock()
    mock_conn = mock_store._conn

    # (cid, name, typ, notnull, dflt, pk)
    malicious_default = (0, "col1", "INT", 0, "1); DROP TABLE nodes; --", 0)

    mock_conn.execute.side_effect = [
        MagicMock(fetchone=lambda: ("sqlite_autoindex_nodes_1",)),  # legacy check
        MagicMock(fetchall=lambda: [malicious_default]),  # PRAGMA table_info
    ]

    # Note: currently this might be caught by the blacklist,
    # but we want to ensure it stays caught or is caught by a better regex.
    with pytest.raises(RuntimeError, match="Unsafe default value detected"):
        TemporalIndex(mock_store, current_sha="abc")

def test_ensure_temporal_friendly_schema_rejects_malicious_name():
    """Verify that malicious column names are rejected."""
    mock_store = MagicMock()
    mock_conn = mock_store._conn

    # (cid, name, typ, notnull, dflt, pk)
    malicious_name = (0, 'col1" --', "INT", 0, None, 0)

    mock_conn.execute.side_effect = [
        MagicMock(fetchone=lambda: ("sqlite_autoindex_nodes_1",)),  # legacy check
        MagicMock(fetchall=lambda: [malicious_name]),  # PRAGMA table_info
    ]

    with pytest.raises(RuntimeError, match="Unsafe column name detected"):
        TemporalIndex(mock_store, current_sha="abc")

def test_ensure_temporal_friendly_schema_rejects_sneaky_injection_default():
    """Verify that sneaky default values that bypass the blacklist are rejected."""
    mock_store = MagicMock()
    mock_conn = mock_store._conn

    # This payload does NOT contain ; -- or /*
    # But it adds a new column 'secret' to the table.
    malicious_default = (0, "col1", "INT", 0, "1, secret TEXT", 0)

    mock_conn.execute.side_effect = [
        MagicMock(fetchone=lambda: ("sqlite_autoindex_nodes_1",)),  # legacy check
        MagicMock(fetchall=lambda: [malicious_default]),  # PRAGMA table_info
    ]

    # If the current logic is weak, this will NOT raise RuntimeError here,
    # but it will result in a vulnerable CREATE TABLE statement later.
    # We want our FIX to make this raise RuntimeError.
    with pytest.raises(RuntimeError, match="Unsafe default value detected"):
        TemporalIndex(mock_store, current_sha="abc")
