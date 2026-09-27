"""Host control-plane CLI: server/token/config/db subcommands (WP2 lifecycle).

Fast, hermetic coverage of the operator surface — the server path is tested
end-to-end (spawn + bearer + build/query) in tests/test_http_mcp_e2e.py; here
we pin the dispatch contract and the env handoff to run_http().
"""

from __future__ import annotations

import sys
from pathlib import Path

from better_code_review_graph.cli import main


def _run(capsys, *argv: str) -> int:
    sys.argv = ["better-code-review-graph", *argv]
    return main()


def test_token_hash_matches_hull_primitive(capsys) -> None:
    from hull_core.auth.tokens import verify_token

    rc = _run(capsys, "token", "hash", "s3cret-token")
    out = capsys.readouterr().out.strip()
    assert rc == 0
    # scrypt hashes are salted per call: verify rather than compare.
    assert verify_token("s3cret-token", out)
    assert not verify_token("wrong-token", out)
    rc2 = _run(capsys, "token", "hash", "s3cret-token")
    out2 = capsys.readouterr().out.strip()
    assert rc2 == 0
    assert out2 != out  # fresh salt per mint


def test_config_path_prints_instance_config(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    rc = _run(capsys, "config", "path")
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == str(Path(tmp_path) / "config.toml")


def test_config_init_writes_then_refuses_without_force(
    capsys, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path))
    rc = _run(capsys, "config", "init")
    assert rc == 0
    assert (Path(tmp_path) / "config.toml").is_file()

    rc = _run(capsys, "config", "init")
    err = capsys.readouterr().err
    assert rc == 2
    assert "error" in err

    rc = _run(capsys, "config", "init", "--force")
    assert rc == 0


def test_config_show_prints_template_when_absent(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRG_CONFIG_DIR", str(tmp_path / "missing"))
    rc = _run(capsys, "config", "show")
    out = capsys.readouterr().out
    assert rc == 0
    assert "[server]" in out  # template content


def test_db_path_prints_graph_db(capsys) -> None:
    rc = _run(capsys, "db", "path")
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out.endswith("graph.db")


def test_server_start_forces_http_transport(capsys, tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        '[server]\nhost = "127.0.0.1"\nport = 61000\nauth = "no-auth"\n'
    )
    monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("MCP_PORT", raising=False)
    seen: dict[str, object] = {}

    def fake_serve_main() -> None:
        seen["transport"] = __import__("os").environ.get("MCP_TRANSPORT")
        seen["host"] = __import__("os").environ.get("MCP_HOST")
        seen["port"] = __import__("os").environ.get("MCP_PORT")

    monkeypatch.setattr("better_code_review_graph.server.serve_main", fake_serve_main)

    rc = _run(capsys, "server", "start", "--host", "127.0.0.1", "--port", "60077")
    assert rc == 0
    assert seen == {"transport": "http", "host": "127.0.0.1", "port": "60077"}


def test_server_start_keyboard_interrupt_is_clean(capsys, monkeypatch) -> None:
    def interrupted() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("better_code_review_graph.server.serve_main", interrupted)
    rc = _run(capsys, "server", "start")
    assert rc == 0


def test_server_start_refuses_no_auth_off_loopback(
    capsys, tmp_path, monkeypatch
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        '[server]\nhost = "127.0.0.1"\nport = 61000\nauth = "no-auth"\n'
    )
    monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    serve_called = False

    def must_not_serve() -> None:
        nonlocal serve_called  # noqa: F841
        serve_called = True  # pragma: no cover

    monkeypatch.setattr("better_code_review_graph.server.serve_main", must_not_serve)
    rc = _run(capsys, "server", "start", "--host", "0.0.0.0")
    err = capsys.readouterr().err
    assert rc == 2
    assert "no-auth" in err and "loopback" in err
    assert serve_called is False


def test_server_start_refuses_no_auth_config_host_off_loopback(
    capsys, tmp_path, monkeypatch
) -> None:
    """Bypass regression: no --host/MCP_HOST, config-sourced host binds."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text(
        '[server]\nhost = "0.0.0.0"\nport = 61000\nauth = "no-auth"\n'
    )
    monkeypatch.setenv("CRG_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    serve_called = False

    def must_not_serve() -> None:
        nonlocal serve_called  # noqa: F841
        serve_called = True  # pragma: no cover

    monkeypatch.setattr("better_code_review_graph.server.serve_main", must_not_serve)
    rc = _run(capsys, "server", "start")
    err = capsys.readouterr().err
    assert rc == 2
    assert "no-auth" in err and "loopback" in err
    assert serve_called is False


def test_unknown_subcommand_is_rc2(capsys) -> None:
    rc = _run(capsys, "nope")
    err = capsys.readouterr().err
    assert rc == 2
    assert "unknown subcommand" in err
