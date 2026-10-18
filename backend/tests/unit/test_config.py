"""Local-only configuration rules (requirement R18, LOCAL_SETUP section 4, test T17)."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def make(**overrides) -> Settings:
    # _env_file=None keeps a developer's local .env out of the test.
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"],
)
def test_loopback_model_urls_are_accepted(url):
    assert make(ollama_base_url=url).ollama_base_url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.5:11434",
        "http://example.com",
        "http://127.0.0.1.evil.com:11434",
        "https://127.0.0.1@evil.com",
        "http://user:pw@127.0.0.1:11434",
        "ftp://127.0.0.1:11434",
        "http://127.0.0.1:11434/api/redirect",
    ],
)
def test_remote_or_tricky_model_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        make(ollama_base_url=url)


@pytest.mark.parametrize("tag", ["gpt-oss:120b-cloud", "qwen3:4b-cloud", "cloud", "kimi-k2:1t-cloud"])
def test_cloud_model_tags_are_rejected(tag):
    with pytest.raises(ValidationError):
        make(ollama_model=tag)


@pytest.mark.parametrize("tag", ["qwen3:4b", "qwen3:1.7b", "qwen3:4b-instruct-2507-q4_K_M"])
def test_local_model_tags_are_accepted(tag):
    assert make(ollama_model=tag).ollama_model == tag


@pytest.mark.parametrize(
    "name",
    ["campaign_context_demo", "campaign_context_e2e", "campaign_context_test_ab12cd34ef56"],
)
def test_known_graph_names_are_accepted(name):
    assert make(falkordb_graph=name).falkordb_graph == name


@pytest.mark.parametrize("name", ["other", "campaign_context_prod", "campaign_context_test_", "x; DROP"])
def test_unknown_graph_names_are_rejected(name):
    with pytest.raises(ValidationError):
        make(falkordb_graph=name)


@pytest.mark.parametrize("host", ["10.0.0.2", "db.example.com", "0.0.0.0"])
def test_non_loopback_database_host_is_rejected(host):
    with pytest.raises(ValidationError):
        make(falkordb_host=host)


def test_origins_must_be_loopback():
    assert make(allowed_origins="http://127.0.0.1:5173").allowed_origin_list == ["http://127.0.0.1:5173"]
    with pytest.raises(ValidationError):
        make(allowed_origins="http://127.0.0.1:5173,https://evil.test")


def test_demo_clock_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        make(demo_as_of="2026-10-15T12:00:00")
    assert make(demo_as_of="2026-10-15T12:00:00Z").demo_as_of.utcoffset() is not None
