"""Review fix C5: the preflight smoke script applies the app's local-only model rules before any request."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "preflight_model_smoke.py"


@pytest.fixture
def smoke(monkeypatch):
    spec = importlib.util.spec_from_file_location("preflight_model_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sent = []
    monkeypatch.setattr(module, "post", lambda path, body, *a, **k: sent.append((path, body)) or {})
    monkeypatch.setattr(module, "chat", lambda *a, **k: sent.append(("chat", a)) or {})
    return module, sent


@pytest.mark.parametrize("model", ["gpt-oss:120b-cloud", "qwen3:4b-cloud", "cloud/qwen3", ""])
def test_cloud_or_empty_model_is_refused_before_any_request(smoke, model):
    module, sent = smoke
    with pytest.raises(SystemExit, match="refused"):
        module.main(["--model", model])
    assert sent == []


def test_the_local_model_passes_the_guard(smoke):
    module, _ = smoke
    assert module.checked_model("qwen3:4b-instruct-2507-q4_K_M") == "qwen3:4b-instruct-2507-q4_K_M"
