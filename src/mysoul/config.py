"""Trusted operator settings; credentials are resolved from the environment only."""

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
    model_call_limit: int = Field(default=100, ge=0)
    token_budget: int = Field(default=50000, ge=0)
    fatigue_enabled: bool = True
    fatigue_per_hour: float = Field(default=0.2, ge=0, le=1)
    recovery_per_hour: float = Field(default=0.4, ge=0, le=1)
    event_capacity: int = Field(default=256, ge=1, le=10000)

    @model_validator(mode="after")
    def sending_requires_identity(self):
        if self.send_enabled and (not self.owner_id or not self.allowed_groups):
            raise ValueError("Sending requires owner identity and an explicit group allowlist")
        return self
