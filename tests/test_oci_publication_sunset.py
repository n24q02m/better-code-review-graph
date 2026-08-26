"""Contracts for retiring new public OCI publication without retiring CRG."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "cd.yml"


def _job_block(workflow: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, name
    return match.group("body")


def test_release_workflow_keeps_packages_without_public_oci_jobs():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "  publish-pypi:" in workflow
    assert "  publish-mcp-registry:" in workflow
    assert "  build-docker:" not in workflow
    assert "  merge-docker:" not in workflow
    assert "DOCKERHUB_IMAGE" not in workflow
    assert "GHCR_IMAGE" not in workflow
    assert "packages: write" not in workflow
    assert "needs: [release, publish-pypi]" in _job_block(
        workflow, "publish-mcp-registry"
    )


def test_registry_metadata_is_pypi_only():
    metadata = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))

    assert [package["registryType"] for package in metadata["packages"]] == ["pypi"]
    serialized = json.dumps(metadata)
    assert "docker.io/n24q02m/better-code-review-graph" not in serialized
    assert "ghcr.io/n24q02m/better-code-review-graph" not in serialized


def test_docs_keep_source_self_hosting_but_mark_public_oci_historical():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert (ROOT / "Dockerfile").is_file()
    assert "Historical public OCI tags are retained" in readme
    assert re.search(
        r"new\s+public Docker Hub/GHCR images are no longer\s+published", readme
    )
    assert "img.shields.io/docker" not in readme
    for guidance in (agents, claude):
        assert "new public OCI images do not" in guidance
        assert "eligible stable releases -> MCP Registry" in guidance
