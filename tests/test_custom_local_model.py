"""Kiểm tra resolver model embedding local theo contract generic."""

import json

import pytest


def _manifest_payload() -> dict:
    return {
        "schema_version": 1,
        "model_id": "acme/tiny-e5",
        "source": "acme/tiny-e5",
        "model_family": "bert",
        "task": "dense",
        "modality": "text",
        "output_dim": 384,
        "output_shape": [384],
        "pooling": "mean",
        "normalization": True,
        "max_seq_len": 512,
        "preprocessor": {
            "kind": "text",
            "config_file": "tokenizer.json",
            "image_size": None,
            "image_mean": None,
            "image_std": None,
        },
        "tokenizer_files": ["tokenizer.json"],
        "artifact_formats": ["onnx"],
        "quantization": None,
        "exporter_version": "test",
    }


def test_empty_plugin_values_use_local_embedding_defaults(monkeypatch):
    from better_code_review_graph.config import Settings

    for key in (
        "LOCAL_EMBEDDING_MODEL",
        "LOCAL_EMBEDDING_DIM",
        "LOCAL_EMBEDDING_MODEL_FILE",
        "LOCAL_EMBEDDING_POOLING",
        "LOCAL_EMBEDDING_NORMALIZE",
    ):
        monkeypatch.setenv(key, "")

    configured = Settings()

    assert configured.local_embedding_model == ""
    assert configured.local_embedding_dim == 0
    assert configured.local_embedding_model_file == "onnx/model.onnx"
    assert configured.local_embedding_pooling == "MEAN"
    assert configured.local_embedding_normalize is True


def test_builtin_model_id_is_not_registered(monkeypatch):
    """ID built-in lấy từ registry, không hardcode một họ model cụ thể."""
    from better_code_review_graph import server
    from better_code_review_graph.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "builtin/reference-text")
    monkeypatch.setattr(
        server,
        "_built_in_model_ids",
        lambda: {"builtin/reference-text"},
    )
    called = []
    monkeypatch.setattr(
        server, "_register_spec", lambda **kwargs: called.append(kwargs)
    )

    server._maybe_register_custom_embed("builtin/reference-text")

    assert called == []


def test_non_qwen_manifest_uses_the_same_registration_path(monkeypatch, tmp_path):
    """Manifest ngoài Qwen đi qua cùng resolver với built-in model."""
    from better_code_review_graph import server
    from better_code_review_graph.config import settings

    model_dir = tmp_path / "tiny-e5"
    model_dir.mkdir()
    (model_dir / "fastretrieval-manifest.json").write_text(
        json.dumps(_manifest_payload()),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "local_embedding_model", str(model_dir))
    monkeypatch.setattr(server, "_built_in_model_ids", lambda: set())
    called = []
    monkeypatch.setattr(
        server, "_register_spec", lambda **kwargs: called.append(kwargs)
    )

    server._maybe_register_custom_embed(str(model_dir))

    assert len(called) == 1
    assert called[0]["model_id"] == "acme/tiny-e5"
    assert called[0]["dim"] == 384
    assert called[0]["pooling"] == "MEAN"
    assert called[0]["normalization"] is True


def test_manifest_registration_is_idempotent(monkeypatch, tmp_path):
    from better_code_review_graph import server

    model_dir = tmp_path / "tiny-e5"
    model_dir.mkdir()
    (model_dir / "fastretrieval-manifest.json").write_text(
        json.dumps(_manifest_payload()),
        encoding="utf-8",
    )
    called = []

    def _built_in_ids():
        return {"acme/tiny-e5"} if called else set()

    monkeypatch.setattr(server, "_built_in_model_ids", _built_in_ids)
    monkeypatch.setattr(
        server, "_register_spec", lambda **kwargs: called.append(kwargs)
    )

    server._maybe_register_custom_embed(str(model_dir))
    server._maybe_register_custom_embed(str(model_dir))

    assert len(called) == 1


def test_custom_model_directory_without_manifest_is_refused(monkeypatch, tmp_path):
    from better_code_review_graph import server
    from better_code_review_graph.config import settings

    model_dir = tmp_path / "missing-manifest"
    model_dir.mkdir()
    monkeypatch.setattr(settings, "local_embedding_model", str(model_dir))
    monkeypatch.setattr(server, "_built_in_model_ids", lambda: set())

    with pytest.raises(ValueError, match="fastretrieval-manifest.json"):
        server._maybe_register_custom_embed(str(model_dir))


def test_custom_model_without_dim_is_refused(monkeypatch):
    from better_code_review_graph import server
    from better_code_review_graph.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "acme/my-embedder")
    monkeypatch.setattr(settings, "local_embedding_dim", 0)
    monkeypatch.setattr(server, "_built_in_model_ids", lambda: set())
    called = []
    monkeypatch.setattr(
        server, "_register_spec", lambda **kwargs: called.append(kwargs)
    )

    server._maybe_register_custom_embed("acme/my-embedder")

    assert called == [], "custom model without a dimension must not be registered"


def test_init_backend_fails_closed_without_dim(monkeypatch):
    from better_code_review_graph import server
    from better_code_review_graph.config import settings
    from better_code_review_graph.embeddings import init_backend

    monkeypatch.setattr(settings, "local_embedding_model", "acme/my-embedder")
    monkeypatch.setattr(settings, "local_embedding_dim", 0)
    monkeypatch.setattr(server, "_built_in_model_ids", lambda: set())
    monkeypatch.setattr(server, "_register_spec", lambda **kwargs: None)

    with pytest.raises(ValueError, match="LOCAL_EMBEDDING_DIM"):
        init_backend(mode="local")


def test_custom_model_is_registered_with_every_declared_field(monkeypatch):
    from better_code_review_graph import server
    from better_code_review_graph.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "acme/my-embedder")
    monkeypatch.setattr(settings, "local_embedding_dim", 512)
    monkeypatch.setattr(settings, "local_embedding_model_file", "onnx/model.onnx")
    monkeypatch.setattr(settings, "local_embedding_pooling", "mean")
    monkeypatch.setattr(settings, "local_embedding_normalize", True)
    monkeypatch.setattr(server, "_built_in_model_ids", lambda: set())

    called = []
    monkeypatch.setattr(
        server, "_register_spec", lambda **kwargs: called.append(kwargs)
    )
    server._maybe_register_custom_embed("acme/my-embedder")

    assert len(called) == 1
    spec = called[0]
    assert spec["model_id"] == "acme/my-embedder"
    assert spec["hf"] == "acme/my-embedder"
    assert spec["dim"] == 512
    assert spec["model_file"] == "onnx/model.onnx"
    assert spec["pooling"] == "MEAN"
    assert spec["normalization"] is True


def test_registering_twice_is_not_fatal(monkeypatch):
    """Khởi động lại trong cùng process không làm server chết."""
    from better_code_review_graph import server
    from better_code_review_graph.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "acme/my-embedder")
    monkeypatch.setattr(settings, "local_embedding_dim", 512)
    monkeypatch.setattr(server, "_built_in_model_ids", lambda: set())

    def _boom(**kwargs):
        raise ValueError("already registered")

    monkeypatch.setattr(server, "_register_spec", _boom)
    server._maybe_register_custom_embed("acme/my-embedder")


def test_invalid_registration_error_is_not_swallowed(monkeypatch):
    from better_code_review_graph import server
    from better_code_review_graph.config import settings

    monkeypatch.setattr(settings, "local_embedding_dim", 512)
    monkeypatch.setattr(settings, "local_embedding_pooling", "INVALID")
    monkeypatch.setattr(server, "_built_in_model_ids", lambda: set())

    def _boom(**kwargs):
        raise ValueError("invalid pooling")

    monkeypatch.setattr(server, "_register_spec", _boom)

    with pytest.raises(ValueError, match="invalid pooling"):
        server._maybe_register_custom_embed("acme/my-embedder")
