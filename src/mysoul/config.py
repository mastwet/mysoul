"""Trusted runtime settings; model credentials live at the provider boundary."""

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from mysoul.domain import Contract


class Settings(Contract):
    data_dir: Path = Path(".local")
    host: Literal["127.0.0.1", "localhost"] = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    owner_id: str = "local-owner"
    backend: Literal["replay", "napcat"] = "replay"
    send_enabled: bool = False
    allowed_groups: set[str] = Field(default_factory=set)
    operator_auth_required: bool = True
    model_call_limit: int | None = Field(default=100, ge=0)
    token_budget: int | None = Field(default=50000, ge=0)
    model_output_limit: int | None = Field(default=None, ge=1)
    context_chars: int = Field(default=131072, ge=4096, le=2097152)
    request_timeout: float = Field(default=120, gt=0, le=600)
    fatigue_enabled: bool = True
    fatigue_per_hour: float = Field(default=0.2, ge=0, le=1)
    recovery_per_hour: float = Field(default=0.4, ge=0, le=1)
    event_capacity: int = Field(default=256, ge=1, le=10000)
    model_mode: Literal["replay", "procedure-replay", "provider"] = "replay"
    load_saved_model: bool = True
    memory_backend: Literal["local", "fixture", "mempalace"] = "local"
    mempalace_config: Path | None = None
    news_sources: set[str] = Field(default_factory=set)

    @classmethod
    def from_environment(cls):
        mapping = {
            "MYSOUL_DATA_DIR": "data_dir",
            "MYSOUL_MODEL_MODE": "model_mode",
            "MYSOUL_PHONE_BACKEND": "backend",
            "MYSOUL_OWNER_ID": "owner_id",
            "MYSOUL_SEND_ENABLED": "send_enabled",
            "MYSOUL_MEMORY_BACKEND": "memory_backend",
            "MYSOUL_MEMPALACE_CONFIG": "mempalace_config",
            "MYSOUL_MODEL_CALL_LIMIT": "model_call_limit",
            "MYSOUL_OPERATOR_AUTH_REQUIRED": "operator_auth_required",
            "MYSOUL_TOKEN_BUDGET": "token_budget",
        }
        values = {field: os.environ[key] for key, field in mapping.items() if key in os.environ}
        if str(values.get("model_call_limit", "")).strip().lower() == "unlimited":
            values["model_call_limit"] = None
        values["allowed_groups"] = {
            g.strip() for g in os.environ.get("MYSOUL_ALLOWED_GROUPS", "").split(",") if g.strip()
        }
        values["news_sources"] = {
            s.strip() for s in os.environ.get("MYSOUL_NEWS_SOURCES", "").split(",") if s.strip()
        }
        return cls.model_validate(values)

    @model_validator(mode="after")
    def sending_requires_identity(self):
        if self.send_enabled and (not self.owner_id or not self.allowed_groups):
            raise ValueError("Sending requires owner identity and an explicit group allowlist")
        return self


class MemorySelection(Contract):
    backend: Literal["local", "mempalace"]
    process_config: Path | None = None

    @model_validator(mode="after")
    def process_required(self):
        if self.backend == "mempalace" and self.process_config is None:
            raise ValueError("MemPalace requires a local process configuration")
        return self


def apply_saved_memory(settings):
    # Explicit environment/constructor settings remain the recovery override.
    if {"memory_backend", "mempalace_config"} & settings.model_fields_set:
        return
    path = settings.data_dir / "memory.settings.json"
    if not path.exists():
        return
    saved = MemorySelection.model_validate_json(path.read_text(encoding="utf-8"))
    settings.memory_backend = saved.backend
    if saved.process_config:
        value = saved.process_config
        settings.mempalace_config = value if value.is_absolute() else path.parent / value
