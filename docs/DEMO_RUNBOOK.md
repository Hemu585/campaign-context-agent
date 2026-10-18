# Demo runbook

How to run the demo walkthrough. The browser test T18 (`frontend/tests/demo-flow.spec.ts`) drives this same click path against the real model and FalkorDB, and passed on 16 Oct 2026. Record a real run: never present precomputed output as a live agent decision, and label any cut or skipped wait in the video.


## 1. Prepare the laptop (about 10 minutes before)

1. **Quit memory-heavy apps completely.** ChatGPT, Discord and Brave keep running in the system tray after their windows close, so quit them from the tray too. Turn off notifications.
2. **Check for an orphaned Ollama runner.** On 16 Oct an orphaned runner held 4.6 GB of memory and made every run slow. Compare the two lists:

   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" | Select-Object ProcessId, ParentProcessId
   Get-Process ollama | Select-Object Id
   ```

   A `llama-server` whose `ParentProcessId` is not one of the `ollama` IDs is orphaned. Stop it with `Stop-Process -Id <ProcessId>`.
3. **Check free memory.** Aim for at least 6,000 MB of free commit before loading the model; the model uses about 4 GB.

   ```powershell
   [int]((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1024)
   ```

## 2. Start a clean demo

Start Docker Desktop first. Then, from the project root:

**Terminal 1 (database and backend):**

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m app.cli reset-demo --confirm campaign_context_demo
.\.venv\Scripts\python.exe -m app.cli seed --dataset demo_v1
.\.venv\Scripts\python.exe -m app.cli preflight
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`reset-demo` deletes only the demo graph, and only when given its exact name; `seed` then reloads the fictional baseline. `preflight` must show 7 × PASS.

**Terminal 2 (UI):**

```powershell
npm --prefix frontend run build
npm --prefix frontend run preview
```

**Terminal 3 (warm the model, about 10 s).** This loads the model with the same settings the app uses:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/chat -Method Post -ContentType 'application/json' -Body '{"model":"qwen3:4b-instruct-2507-q4_K_M","messages":[{"role":"user","content":"Reply with OK."}],"stream":false,"think":false,"keep_alive":"30m","options":{"num_ctx":8192}}'
```

Open **http://127.0.0.1:5173** with the browser window at about 1280×720. A session remembered from earlier takes is forgotten automatically after the reset. Before recording, check:

- The stamp reads "Synthetic demo data · As of 15 Oct 2026, 17:30 IST · fixed demo clock · revision 1".
- The pills read "FalkorDB connected" and "Model qwen3:4b".
- The campaign is "Luma Autumn Launch · Luma Skin", and its slot says "Open. Drafts are not approvals."
- Decision history is empty.

## 3. Click path

Runs take 30–60 s on this laptop. Leave the waits in, or label them if you cut.

| Time | Do this | You should see / say |
| --- | --- | --- |
| 0:00 | Point at the campaign card | Asha Pine dropped out. Luma needs one Hindi Instagram beauty reel, delivered 20 Oct 09:00 → 23 Oct 18:00 IST, within ₹25,000 |
| 0:25 | Click **Run agent**. The suggested prompt is already filled: "Find a replacement for this campaign and explain any conflicts." | Live steps: Read campaign requirements → Evaluated every candidate → Inspected evidence · cr_02 → Staged a draft proposal · cr_02. Result: Mira Vale, Noor Finch, Ada Bloom, with a draft for Mira. The board is labelled "Agent run …" |
| 1:10 | On Tara Reed's row, click **View evidence**, then **Graph paths** | The "Competitor conflict — explains the result" path: Tara → exclusive agreement agr_cr03 → Noro Glow → COMPETES_WITH → Luma Skin → RUNS → the campaign. Open **Sources** to show `src_agreement_cr03_v1`, observed 15 Oct 2026. Press Escape |
| 1:40 | On Mira's row, click **Reject**. Keep "This campaign only", type a reason and click **Save rejection** | The banner "Information changed — run again." appears |
| 1:55 | Click **New session** in the header, then **Run agent** | Noor is now first. Mira is under "Excluded by your remembered rejections". **Decision history** shows the campaign-scope rejection and explains that a brand rejection would cover all of Luma's campaigns |
| 2:15 | Open **Demo data**. On "Agreement with Noro Glow · agr_cr03" click **Edit**, set **End (IST)** to 19 Oct 2026 23:59:59, type a reason and click **Save new version** | The banner names the new source `src_agreement_cr03_v2`. Back on **Candidates**: "Information changed — run again.", and the old draft's Review button is disabled |
| 2:30 | Click **Run agent again** in the banner | Tara is now first at ₹15,000, with a draft for Tara |
| 2:55 | On Tara's row, click **Review proposal** | "Current"; fee ₹15,000 within ₹25,000; "Approves an internal replacement proposal. Does not contact or book the creator." |
| 3:10 | Click **Approve proposal**, then **Close** | "Approved and saved." The campaign card shows "✓ Filled by approved proposal for Tara Reed" |
| 3:25 | **Restart segment.** In Terminal 1 press Ctrl+C, run `docker compose restart falkordb`, wait about 10 s, then start uvicorn again. Reload the page | The same conversation, the rejection and the approval in Decision history, and the filled slot. For a stronger test use `docker compose up -d --force-recreate falkordb`, which keeps the data volume |
| 3:50 | Show the README and its Limits section | Local model and FalkorDB, fictional data, a single operator, traceable sources |

## 4. If something goes wrong

| What you see | What to do |
| --- | --- |
| "The local model is unavailable" | Start Ollama from the Start menu, wait a few seconds, then warm the model again |
| A run takes longer than 60 s | Memory pressure: wait. A run stops at 180 s and shows "Run failed" with **Retry**. Never present a failed run as a success |
| "The backend is no longer working on this run" | Click **Cancel run**, then **Run agent** |
| "FalkorDB is not reachable" | Start Docker Desktop, then run `docker compose up -d` |
| "The graph has no demo data" | Run the `seed` command from step 2 |
| State left over from an earlier take | Stop uvicorn, run `reset-demo` and `seed` again, start uvicorn and reload the page |

## 5. After recording

- Keep a backup copy of the video, and check that the final link opens for someone who is not logged in.
- For another take, repeat step 2's `reset-demo` and `seed`.
- To stop everything: press Ctrl+C in each terminal, then run `docker compose stop`. Never run `docker compose down -v`, which deletes the data volume.
- To free the model's memory:

  ```powershell
  Invoke-RestMethod http://127.0.0.1:11434/api/generate -Method Post -ContentType 'application/json' -Body '{"model":"qwen3:4b-instruct-2507-q4_K_M","keep_alive":0}'
  ```
