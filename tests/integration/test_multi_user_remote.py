"""Per-sub credential + DB isolation in crg remote multi-user mode."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_two_subs_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    from better_code_review_graph.credential_state import (
        db_path_for_sub,
        read_for_sub,
        store_for_sub,
    )

    store_for_sub("user_a", {"GEMINI_API_KEY": "k1"})
    store_for_sub("user_b", {"GEMINI_API_KEY": "k2"})

    assert read_for_sub("user_a") == {"GEMINI_API_KEY": "k1"}
    assert read_for_sub("user_b") == {"GEMINI_API_KEY": "k2"}

    pa = db_path_for_sub("user_a")
    pb = db_path_for_sub("user_b")
    assert pa != pb
    assert "user_a" in str(pa)
    assert "user_b" in str(pb)


@pytest.mark.integration
def test_save_credentials_uses_sub_when_public_url_set(tmp_path, monkeypatch):
    monkeypatch.setenv("CRG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_URL", "https://crg.example.com")
    from better_code_review_graph.credential_state import (
        read_for_sub,
        save_credentials,
    )

    save_credentials({"GEMINI_API_KEY": "k1"}, {"sub": "user_a"})
    save_credentials({"GEMINI_API_KEY": "k2"}, {"sub": "user_b"})

    assert read_for_sub("user_a")["GEMINI_API_KEY"] == "k1"
    assert read_for_sub("user_b")["GEMINI_API_KEY"] == "k2"
