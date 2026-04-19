"""E2E MCP protocol test -- hit running better-code-review-graph HTTP server via StreamableHTTP + OAuth PKCE.

Flow:
1. Generate PKCE pair
2. GET /authorize -> parse HTML, extract nonce from inline JS.
3. POST /authorize?nonce=<nonce> with JSON body = existing credentials -> get auth_code
4. POST /token with code + code_verifier -> get JWT
5. Open MCP session with Bearer JWT, call each tool, print results

Adapted from mnemo-mcp/tests/e2e_mcp_protocol_test.py for better-code-review-graph.
Tools: graph, query, review, config, help.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import secrets
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BASE_URL = os.environ.get("CRG_BASE_URL", "http://127.0.0.1:60052").rstrip("/")
REPO_ROOT = os.environ.get(
    "CRG_TEST_REPO_ROOT",
    "C:/Users/n24q02m-wlap/projects/better-code-review-graph",
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


async def obtain_jwt() -> str:
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(16)
    redirect_uri = "http://localhost:9999/cb"
    client_id = "e2e-test"

    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.get(
            f"{BASE_URL}/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        print(f"[1] GET /authorize -> {resp.status_code}")
        assert resp.status_code == 200, resp.text[:300]

        match = re.search(r"/authorize\?nonce=([A-Za-z0-9_\-]+)", resp.text)
        assert match, f"Nonce not found in HTML: {resp.text[:500]}"
        nonce = match.group(1)
        print(f"[1] nonce={nonce[:16]}...")

        from mcp_core.storage.config_file import read_config

        existing = read_config("better-code-review-graph") or {}
        print(f"[2] Re-submitting existing credentials: {list(existing.keys())}")

        resp = await http.post(
            f"{BASE_URL}/authorize",
            params={"nonce": nonce},
            json=existing,
        )
        print(f"[3] POST /authorize -> {resp.status_code}")
        assert resp.status_code == 200, resp.text[:500]
        body = resp.json()
        redirect_url = body["redirect_url"]
        code_match = re.search(r"[?&]code=([^&]+)", redirect_url)
        assert code_match, redirect_url
        auth_code = code_match.group(1)
        print(f"[3] auth_code={auth_code[:16]}...")

        resp = await http.post(
            f"{BASE_URL}/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
            },
        )
        print(f"[4] POST /token -> {resp.status_code}")
        assert resp.status_code == 200, resp.text[:500]
        tok = resp.json()
        jwt = tok.get("access_token")
        assert jwt, tok
        print(f"[4] JWT obtained: {jwt[:40]}...")
        return jwt


def _short(s: Any, n: int = 240) -> str:
    text = str(s)
    text = text.replace("\n", " ")
    if len(text) <= n:
        return text
    return text[:n] + "..."


async def call_tool(
    session: ClientSession,
    name: str,
    args: dict | None = None,
    timeout: float = 60.0,
) -> dict:
    result: dict = {"tool": name, "args": args}
    try:
        resp = await asyncio.wait_for(
            session.call_tool(name, arguments=args or {}), timeout=timeout
        )
        parts = []
        for item in resp.content:
            t = getattr(item, "text", None)
            if t is not None:
                parts.append(t)
            else:
                parts.append(str(item))
        combined = "\n".join(parts)
        result["status"] = "OK" if not resp.isError else "ERROR"
        result["response"] = combined
        result["is_error"] = bool(resp.isError)
    except TimeoutError:
        result["status"] = "TIMEOUT"
        result["response"] = f"Tool call exceeded {timeout}s"
    except Exception as e:
        result["status"] = "EXCEPTION"
        result["response"] = f"{type(e).__name__}: {e}"
    return result


async def main() -> list[dict]:
    jwt = await obtain_jwt()

    headers = {"Authorization": f"Bearer {jwt}"}
    print(f"\n[MCP] Connecting to {BASE_URL}/mcp with Bearer auth...")

    async with streamablehttp_client(f"{BASE_URL}/mcp", headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] Initialized")

            tools_resp = await session.list_tools()
            names = [t.name for t in tools_resp.tools]
            print(f"[MCP] Tools available: {names}")

            # Base tests: help topics, config actions, graph lifecycle, query actions, review
            tests: list[tuple[str, dict, float]] = [
                # help ------------------------------------------------------
                ("help", {}, 30.0),
                ("help", {"topic": "graph"}, 30.0),
                ("help", {"topic": "query"}, 30.0),
                ("help", {"topic": "review"}, 30.0),
                ("help", {"topic": "config"}, 30.0),
                # config ----------------------------------------------------
                ("config", {"action": "status", "repo_root": REPO_ROOT}, 30.0),
                ("config", {"action": "setup_status"}, 30.0),
                ("config", {"action": "setup_complete"}, 30.0),
                (
                    "config",
                    {"action": "set", "key": "log_level", "value": "INFO"},
                    30.0,
                ),
                # graph -----------------------------------------------------
                # build the graph for this repo (fast: small python codebase)
                (
                    "graph",
                    {
                        "action": "build",
                        "full_rebuild": True,
                        "repo_root": REPO_ROOT,
                    },
                    180.0,
                ),
                ("graph", {"action": "stats", "repo_root": REPO_ROOT}, 30.0),
                ("graph", {"action": "update", "repo_root": REPO_ROOT}, 120.0),
                # query -----------------------------------------------------
                (
                    "query",
                    {
                        "action": "search",
                        "search_query": "config",
                        "limit": 5,
                        "repo_root": REPO_ROOT,
                    },
                    60.0,
                ),
                (
                    "query",
                    {
                        "action": "query",
                        "pattern": "file_summary",
                        "target": "src/better_code_review_graph/server.py",
                        "repo_root": REPO_ROOT,
                    },
                    30.0,
                ),
                (
                    "query",
                    {
                        "action": "impact",
                        "changed_files": ["src/better_code_review_graph/server.py"],
                        "max_depth": 2,
                        "max_results": 50,
                        "repo_root": REPO_ROOT,
                    },
                    30.0,
                ),
                (
                    "query",
                    {
                        "action": "large_functions",
                        "min_lines": 30,
                        "limit": 5,
                        "repo_root": REPO_ROOT,
                    },
                    30.0,
                ),
                # review ----------------------------------------------------
                (
                    "review",
                    {
                        "changed_files": ["src/better_code_review_graph/server.py"],
                        "max_depth": 1,
                        "include_source": False,
                        "max_lines_per_file": 50,
                        "repo_root": REPO_ROOT,
                    },
                    60.0,
                ),
            ]

            results = []
            for tool_name, args, timeout in tests:
                print(f"\n>>> Calling {tool_name}({args})")
                r = await call_tool(session, tool_name, args, timeout=timeout)
                results.append(r)
                print(f"    status={r['status']}")
                print(f"    response={_short(r['response'], 240)}")

            # Embed pass -- may hit cloud API, allow failure to surface as FAIL but
            # do not block other tests. Run last because it mutates the embedding
            # store.
            print("\n>>> Calling graph(embed)")
            embed_result = await call_tool(
                session,
                "graph",
                {"action": "embed", "repo_root": REPO_ROOT},
                timeout=180.0,
            )
            results.append(embed_result)
            print(f"    status={embed_result['status']}")
            print(f"    response={_short(embed_result['response'], 240)}")

            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            pass_count = 0
            for r in results:
                status = "PASS" if r["status"] == "OK" else "FAIL"
                if status == "PASS":
                    pass_count += 1
                print(f"[{status}] {r['tool']}({r['args']}) -> {r['status']}")
            print(f"\nTotal: {pass_count}/{len(results)} PASS")

            return results


if __name__ == "__main__":
    asyncio.run(main())
