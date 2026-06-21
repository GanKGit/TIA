# TIA Runbook - Trade Investigative Agents

This is the operating guide for the TIA MVP demo. TIA validates and investigates trading-system behavior using a fixed MVP control catalog and specialist agents. Document-based PRA/base loading has been removed from this build.

## 1. What TIA Demonstrates

TIA demonstrates an agentic compliance investigation flow:

1. Prepare demo exchange/market/trading state.
2. Run deterministic validation agents against the trading system.
3. Let investigation agents decide which evidence paths to inspect.
4. Challenge the evidence for contradictions.
5. Produce an auditable final finding with confidence and remediation.

## 2. Current MVP Scope

- 9 active validation agents.
- Positive and negative investigation demo cases.
- Local demo stack startup from the UI.
- Direct validation evidence checks.
- How It Works explanation inside the UI.
- FastAPI path for non-UI execution.

## 3. Removed Scope

The following are intentionally removed:

- Base regulation loading.
- PRA update loading.
- YAML filter files.
- `/knowledge/learn` endpoint.
- PRA/base regulatory PDFs.
- Agent deployment scripts for deferred PRA controls.

The term `knowledge` may still appear in API/model names because the validator keeps a versioned in-memory control catalog. It is not RAG and it is not document learning.

## 4. Setup

```powershell
cd "C:\GAN\Learn\ML & AI\HCL Hackathon  - 2026\Project\TIA"
$Python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $Python --version  # Expected: Python 3.12.x

# Run this line only when replacing an existing virtual environment.
if (Test-Path .venv) { Remove-Item .venv -Recurse -Force }

& $Python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python --version  # Verify the activated environment also uses Python 3.12.x
pip install -r requirements.txt
```

Using the explicit Windows Python path prevents an MSYS2 Python earlier on `PATH`
from creating a Unix-style `.venv\bin` directory instead of `.venv\Scripts`.

## 5. Start UI

```powershell
python -m streamlit run app\ui.py
```

Use the sidebar in this order:

1. **Demo Stack**: start and health-check the local demo stack.
2. **Investigation Console**: run prepared positive or negative investigation cases.
3. **Validation Evidence**: run direct validation checks.
4. **How It Works**: explain the end-to-end flow during the demo.

## 6. Start API Without UI

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:create_api_app --factory --reload --host 127.0.0.1 --port 8602
```

Useful commands:

```powershell
Invoke-RestMethod "http://127.0.0.1:8602/health"
Invoke-RestMethod "http://127.0.0.1:8602/agents" | ConvertTo-Json -Depth 20
Invoke-RestMethod "http://127.0.0.1:8602/knowledge/current" | ConvertTo-Json -Depth 20
```

Run a direct validation:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8602/validations" `
  -ContentType "application/json" `
  -Body '{"system_id":"demo-trading-system","dry_run":true}' | ConvertTo-Json -Depth 20
```

Run an investigation:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8602/investigations" `
  -ContentType "application/json" `
  -Body '{"system_id":"demo-trading-system","preset":"order_control_failure","dry_run":true}' | ConvertTo-Json -Depth 20
```

## 7. Demo Cases

Positive case:

- `market_stress_incident`
- Expected result: pass.
- Shows crossed/locked/one-sided market stress handled correctly.

Negative case:

- `order_control_failure`
- Expected result: fail.
- Injects duplicate-order and bad-price evidence so the agents identify real failures from the scenario data.

Additional prepared cases:

- `order_anomaly_incident`
- `market_stress_failure`

## 8. Active Validation Controls

| ID | Control | Agent |
| --- | --- | --- |
| CTRL-001 | Parent-child orders | parent-child-agent |
| CTRL-002 | Duplicate orders | duplicate-order-agent |
| CTRL-003 | Bad-price breach | bad-price-breach-agent |
| CTRL-004 | Kill switch | kill-switch-agent |
| CTRL-005 | Maximum evaluation frequency | max-evaluation-frequency-agent |
| CTRL-006 | Market order check | market-order-check-agent |
| STRESS-001 | Crossed market | crossed-market-agent |
| STRESS-002 | Locked market | locked-market-agent |
| STRESS-003 | One-sided market | one-sided-market-agent |

## 9. Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 10. Demo Talk Track

TIA is not a document loader now. It is an agentic investigation platform. The demo value is that multiple agents traverse different evidence paths, call deterministic control tools, inspect the trading-system state, challenge the evidence, and synthesize a final audit-ready finding.
