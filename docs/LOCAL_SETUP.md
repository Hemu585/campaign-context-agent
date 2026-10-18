# Local setup and zero-spend preflight

Local setup for the Campaign Context Agent.

## 1. Inspect first

Record OS, CPU, total/free RAM, free disk, GPU/VRAM when discoverable, Python, Node, Docker/Compose and Ollama. Do not inspect or print credentials. Windows is the first documentation target; detect the actual machine rather than assuming it.

PowerShell examples:

```powershell
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
Get-CimInstance Win32_Processor | Select-Object Name
Get-CimInstance Win32_VideoController | Select-Object Name
Get-PSDrive -PSProvider FileSystem
docker version
docker compose version
python --version
node --version
ollama --version
```

GPU detection alone is not proof of usable model acceleration. Use `ollama ps` while a model is loaded and record actual observed memory/speed. Download size is not total inference RAM. No minimum-hardware guarantee is made here.

Use an existing no-additional-cost container runtime, or Docker Engine on a compatible Linux environment. Do not purchase Docker Desktop or assume every commercial-use situation is free. Do not install a paid plan to satisfy this document. If environment changes need the user's action, explain the precise missing component.

## 2. FalkorDB

Suggested `compose.yaml` to create and verify:

```yaml
services:
  falkordb:
    image: ${FALKORDB_IMAGE:-falkordb/falkordb:latest}
    ports:
      - "127.0.0.1:6379:6379"
      - "127.0.0.1:3001:3000"
    environment:
      REDIS_ARGS: "--dir /data --appendonly yes --appendfsync everysec"
    volumes:
      - campaign_context_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  campaign_context_data:
```

The official repository README and deployment docs show differing persistence-directory examples. This proposal sets the data directory explicitly instead of relying on an assumed default. Confirm that the selected image honors it and supports the persistence configuration. If it does not, fix the setup from the pinned image's actual behavior and document the reason.

```powershell
docker compose up -d
docker compose ps
docker compose exec falkordb redis-cli CONFIG GET dir
docker compose exec falkordb redis-cli CONFIG GET appendonly
```

Expected configuration: directory `/data` and appendonly `yes`; then verify graph persistence, not just these flags. The optional database browser is at `http://127.0.0.1:3001`. Use the application for demo edits so revision/source rules are preserved.

Use `latest` only for the first resolution if needed. Record and pin the tested image digest/tag for reproducibility in `.env.example` and the final README. Do not publish an untested tag as a supported release. This loopback-only synthetic setup is not a production database deployment.

## 3. Local Ollama

Use official installation instructions for the detected OS. Run Ollama on the host alongside the backend to avoid container-to-host networking differences.

Set `OLLAMA_NO_CLOUD=1` in the Ollama server's environment and restart that server. A variable set only in the backend's `.env` does not configure an already-running Ollama process. On Windows, set it in the user environment and restart Ollama; on Linux, use the service environment or the shell actually launching it. Check the server logs/configuration for local-only mode. Merge configuration safely; do not overwrite unrelated settings.

First model candidate:

```powershell
ollama pull qwen3:4b
ollama list
ollama run qwen3:4b
```

> **Selected after measurement (design decision D17):** `qwen3:4b-instruct-2507-q4_K_M`. The `qwen3:4b` tag is the thinking build. On the test laptop it took about 22 s per tool turn, against about 1.4 s for the instruct build. Pull the instruct tag; the [root README](../README.md) has the verified setup.

Use the model smoke tool described below, not an ordinary chat answer, to verify function/tool calling. If the machine cannot handle it, test `qwen3:1.7b` as a smaller candidate. A smaller model is acceptable only if it passes the same correctness and tool-use checks. Model choice and context window must fit measured resources.

If both fail or are too slow, stop at the real limitation and request another existing computer or a user-chosen no-spend option. Do not add a hosted fallback, pay-as-you-go key, cloud-tagged model, or hardcoded answer. The diagnostic graph view can be complete while the agent gate remains blocked.

## 4. Application configuration to implement

```dotenv
APP_ENV=local
DEMO_MODE=true
DEMO_AS_OF=2026-10-15T12:00:00Z
FALKORDB_HOST=127.0.0.1
FALKORDB_PORT=6379
FALKORDB_GRAPH=campaign_context_demo
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
ALLOWED_ORIGINS=http://127.0.0.1:5173
AGENT_MAX_TURNS=8
AGENT_MAX_TOOL_CALLS=12
AGENT_RUN_TIMEOUT_SECONDS=180
```

Do not include paid-provider API key fields. Reject model endpoints outside a validated loopback hostname/IP, unexpected ports unless explicitly configured locally, cloud-tagged models, and redirect-based endpoint escapes. The server validates the selected model is installed locally before a run. Record the resolved model digest and tested context settings.

## 5. Python/backend target commands

Implement a backend package with a `pyproject.toml`, checked dependency lock and CLI under `app.cli`. From the project root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e backend
.\.venv\Scripts\python.exe -m app.cli preflight
.\.venv\Scripts\python.exe -m app.cli seed --dataset demo_v1
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

On Linux/macOS use `.venv/bin/python` and create the venv with an appropriate installed Python. Do not change PowerShell execution policy just to activate a venv; using its Python executable is sufficient.

The final locked dependencies must include what the supplied tests need. Seed paths must resolve relative to the project/package, not a fragile current-directory assumption. Never reseed or reset on every API startup.

## 6. Frontend target commands

Once the frontend is installed and locked:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Use the exact documented UI origin; do not silently jump to another port and break CORS. If a port is occupied, explain and choose a consistent alternate local configuration without killing unrelated processes. Bundle fonts/icons/assets locally.

## 7. Verification commands to implement

- `python -m app.cli verify-model`: real local tool-call smoke scenarios, model digest and timings.
- `python -m pytest backend/tests`: unit and actual FalkorDB integration tests; explicit skips mean incomplete coverage.
- A documented Playwright command for the essential UI flow, with its browser downloaded during setup.
- `python -m app.cli preflight`: validates services, schema, graph and local model configuration without overwriting data.

On Windows substitute the venv Python path. These names are required CLI contracts, not currently runnable commands in this package.

## 8. Persistence and offline proof

Save a rejection and an approval in separate test scenarios. Restart backend and FalkorDB; verify their saved effects. Recreate the database container using the same named volume and repeat. Do not use `down -v`, `docker system prune`, or remove the volume. Verify pending runs become interrupted on restart.

After downloads, disconnect external networking or observe an equivalent local-only execution and complete a real demo run. All inference, graph reads/writes and source rendering must remain local. Internet/electricity and existing hardware costs still exist; zero additional spend means no new service bill.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Docker daemon unavailable | Check the existing runtime; do not reinstall/destructively reset automatically |
| Data missing after restart | Verify explicit dir, named volume and persistence; restore from safe fixture only if this is a disposable test graph |
| Model endpoint unreachable | Confirm host Ollama is running on loopback and correct port |
| Model memory error | Reduce bounded context or evaluate the smaller candidate; retain correctness gates |
| Tool-call failures | Inspect structured model replies, selected tag/template and runtime support; do not conceal them |
| Browser requests blocked | Match exact UI origin, Host and nonce; do not replace the policy with wildcard CORS |
| Slow first request | Separate cold loading from warm execution and show a real loading state |
