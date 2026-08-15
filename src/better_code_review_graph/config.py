"""Cấu hình cho backend embedding cục bộ của CRG."""

from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Các trường LOCAL_* cho model embedding người dùng tự cung cấp.

    CRG không có đường reranker cục bộ, vì vậy cấu hình này cố ý chỉ chứa
    embedding. Model ngoài registry phải khai báo dimension hoặc cung cấp
    ``fastretrieval-manifest.json`` trong thư mục artifact.
    """

    local_embedding_model: str = ""
    local_embedding_dim: int = 0
    local_embedding_model_file: str = "onnx/model.onnx"
    local_embedding_pooling: str = "MEAN"
    local_embedding_normalize: bool = True

    model_config = {"env_prefix": "", "case_sensitive": False}

    @model_validator(mode="before")
    @classmethod
    def _empty_plugin_values_use_defaults(cls, values: Any) -> Any:
        """Treat unset optional plugin interpolation values as missing."""
        if not isinstance(values, dict):
            return values
        values = values.copy()
        for field in (
            "local_embedding_model",
            "local_embedding_dim",
            "local_embedding_model_file",
            "local_embedding_pooling",
            "local_embedding_normalize",
        ):
            if values.get(field) == "":
                values.pop(field)
        return values


settings = Settings()
