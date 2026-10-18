"""The frontend's TypeScript types are generated from frontend/openapi.json; it must match the app."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_openapi", ROOT / "scripts" / "export_openapi.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_openapi_matches_the_running_app():
    exporter = load_exporter()
    committed = (ROOT / "frontend" / "openapi.json").read_text(encoding="utf-8")
    assert committed == exporter.render(exporter.current_schema()), (
        "frontend/openapi.json is stale: run scripts/export_openapi.py and npm --prefix frontend run gen:api")


def test_every_route_declares_a_typed_success_response():
    schema = load_exporter().current_schema()
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            ok = next(code for code in op["responses"] if code.startswith("2"))
            content = op["responses"][ok].get("content", {}).get("application/json", {})
            assert content.get("schema"), f"{method.upper()} {path} has an untyped success response"
