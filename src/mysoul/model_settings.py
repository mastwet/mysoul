"""Operator model configuration, redacted views and atomic local secret storage."""

import ctypes
import json
import os
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator

from mysoul.domain import Contract
from mysoul.storage import Conflict


class ModelUpdate(Contract):
    expected_version: int = Field(ge=0)
    mode: Literal["replay", "procedure-replay", "provider"]
    url: str = Field(default="", max_length=2048)
    model: str = Field(default="", max_length=200)
    api_key: SecretStr = Field(default=SecretStr(""), max_length=8192)
    output_token_limit: int | None = Field(default=None, ge=1)
    token_budget: int | None = Field(default=None, ge=0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        value = value.strip().rstrip("/")
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)
            or "\\" in value
            or parsed.scheme not in {"http", "https"}
            or (
                parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            )
        ):
            raise ValueError("Use HTTPS or a loopback HTTP endpoint without credentials")
        _ = parsed.port
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value):
        value = value.strip()
        if any(ord(c) < 32 for c in value):
            raise ValueError("Invalid model identifier")
        return value

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value):
        raw = value.get_secret_value().strip()
        if any(ord(c) < 33 or ord(c) > 126 for c in raw):
            raise ValueError("Invalid API key")
        return SecretStr(raw)


class ModelConfiguration(Contract):
    version: int = 0
    mode: Literal["replay", "procedure-replay", "provider"] = "replay"
    url: str = ""
    model: str = ""
    api_key: SecretStr = SecretStr("")
    source: Literal["runtime", "environment", "local"] = "runtime"
    output_token_limit: int | None = Field(default=None, ge=1)
    token_budget: int | None = Field(default=None, ge=0)

    def public(self):
        return {
            "version": self.version,
            "mode": self.mode,
            "url": self.url,
            "model": self.model,
            "key_present": bool(self.api_key.get_secret_value()),
            "source": self.source,
            "output_token_limit": self.output_token_limit,
            "token_budget": self.token_budget,
        }

    def create_model(self):
        if self.mode == "provider":
            from mysoul.provider import OpenAICompatibleModel

            return OpenAICompatibleModel(self.url, self.model, self.api_key.get_secret_value())
        if self.mode == "procedure-replay":
            from mysoul.evolution import ProcedureReplayModel

            return ProcedureReplayModel()
        from mysoul.model import ReplayModel

        return ReplayModel()


def windows_protect(data: bytes, *, decrypt=False):
    """DPAPI user-bound encryption; never fall back to plaintext on Windows."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = (
        ctypes.windll.crypt32.CryptUnprotectData
        if decrypt
        else ctypes.windll.crypt32.CryptProtectData
    )
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError("Local credential protection unavailable")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class ModelSettings:
    def __init__(self, directory: Path):
        self.path = directory / "model.settings"

    def load(self, settings):
        if settings.load_saved_model and self.path.exists():
            data = self.path.read_bytes()
            if os.name == "nt":
                data = windows_protect(data, decrypt=True)
            try:
                configuration = ModelConfiguration.model_validate_json(data)
                if "token_budget" not in configuration.model_fields_set:
                    configuration.token_budget = settings.token_budget
                if "output_token_limit" not in configuration.model_fields_set:
                    configuration.output_token_limit = settings.model_output_limit
                return configuration
            except ValueError:
                raise ValueError("Saved model settings cannot be read") from None
        if settings.model_mode == "provider":
            validated = ModelUpdate(
                expected_version=0,
                mode="provider",
                url=os.environ.get("MYSOUL_PROVIDER_URL", ""),
                model=os.environ.get("MYSOUL_MODEL", ""),
                api_key=os.environ.get("MYSOUL_API_KEY", ""),
                output_token_limit=settings.model_output_limit,
                token_budget=settings.token_budget,
            )
            return self.resolve(validated, ModelConfiguration()).model_copy(
                update={"version": 0, "source": "environment"}
            )
        return ModelConfiguration(
            mode=settings.model_mode,
            output_token_limit=settings.model_output_limit,
            token_budget=settings.token_budget,
        )

    def resolve(self, update, current):
        if update.expected_version != current.version:
            raise Conflict("Model settings changed")
        key = update.api_key
        if not key.get_secret_value():
            if current.url == update.url:
                key = current.api_key
            elif update.mode == "provider":
                raise ValueError("Enter an API key when changing the endpoint")
        if update.mode == "provider" and not (
            update.url and update.model and key.get_secret_value()
        ):
            raise ValueError("Provider endpoint, model and API key required")
        return ModelConfiguration(
            version=current.version + 1,
            mode=update.mode,
            url=update.url,
            model=update.model,
            api_key=key,
            source="local",
            output_token_limit=(
                update.output_token_limit
                if "output_token_limit" in update.model_fields_set
                else current.output_token_limit
            ),
            token_budget=(
                update.token_budget
                if "token_budget" in update.model_fields_set
                else current.token_budget
            ),
        )

    def save(self, configuration):
        values = configuration.model_dump(mode="json")
        values["api_key"] = configuration.api_key.get_secret_value()
        data = json.dumps(values).encode("utf-8")
        if os.name == "nt":
            data = windows_protect(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".model-")
        try:
            with os.fdopen(descriptor, "wb") as file:
                os.chmod(temporary, 0o600)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
