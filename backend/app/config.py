"""Local-only runtime settings.

Every network endpoint is validated as loopback so the app can never be pointed
at a remote database or a hosted model, and cloud-tagged models are refused
(requirement R18, LOCAL_SETUP section 4).
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GRAPH_NAME_RE = re.compile(r"^campaign_context_(demo|e2e|persist|test_[a-z0-9_]{1,40})$")
# A tag segment equal to "cloud" (e.g. "gpt-oss:120b-cloud") marks Ollama cloud models.
CLOUD_TAG_RE = re.compile(r"(^|[:\-_/])cloud($|[:\-_/])", re.IGNORECASE)


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def check_loopback_http_url(url: str, *, allow_path: bool = False) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported scheme in {url!r}")
    if parts.username or parts.password:
        raise ValueError("credentials in URLs are not allowed")
    if not is_loopback_host(parts.hostname):
        raise ValueError(f"{url!r} is not a loopback address")
    if not allow_path and parts.path not in {"", "/"}:
        raise ValueError("the base URL must not contain a path")
    if parts.query or parts.fragment:
        raise ValueError("the base URL must not contain a query or fragment")
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    demo_mode: bool = True
    demo_as_of: datetime = datetime.fromisoformat("2026-10-15T12:00:00+00:00")
    freshness_days: int = 30

    falkordb_host: str = "127.0.0.1"
    falkordb_port: int = 6379
    falkordb_graph: str = "campaign_context_demo"
    query_timeout_ms: int = 5000

    ollama_base_url: str = "http://127.0.0.1:11434"
    # Non-thinking instruct build; see design decision D17 for the measured reason.
    ollama_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    ollama_num_ctx: int = 8192
    ollama_num_predict: int = 512
    ollama_seed: int = 42

    allowed_origins: str = "http://127.0.0.1:5173"
    agent_max_turns: int = 8
    agent_max_tool_calls: int = 12
    agent_run_timeout_seconds: int = 180

    @field_validator("falkordb_host")
    @classmethod
    def _db_host_is_loopback(cls, value: str) -> str:
        if not is_loopback_host(value):
            raise ValueError(f"FALKORDB_HOST {value!r} is not a loopback address")
        return value

    @field_validator("falkordb_graph")
    @classmethod
    def _graph_name_is_known(cls, value: str) -> str:
        if not GRAPH_NAME_RE.match(value):
            raise ValueError(f"graph name {value!r} is not an allowed campaign_context_* name")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def _model_url_is_loopback(cls, value: str) -> str:
        return check_loopback_http_url(value)

    @field_validator("ollama_model")
    @classmethod
    def _model_is_not_cloud(cls, value: str) -> str:
        if not value or CLOUD_TAG_RE.search(value):
            raise ValueError(f"model {value!r} is empty or a cloud model; only local models are allowed")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def _origins_are_loopback(cls, value: str) -> str:
        for origin in (o.strip() for o in value.split(",") if o.strip()):
            check_loopback_http_url(origin)
        return value

    @field_validator("demo_as_of")
    @classmethod
    def _clock_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("DEMO_AS_OF must include a timezone (e.g. 2026-10-15T12:00:00Z)")
        return value

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
