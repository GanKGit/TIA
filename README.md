# TIA - Trade Investigative Agents

TIA is a demo-oriented agentic investigation platform for trading-system compliance controls. It starts a local demo stack, runs specialist validation agents against trading and market scenarios, and synthesizes an evidence-backed investigation finding.

## Current MVP Scope

- Fixed TIA MVP control catalog initialized at startup.
- 9 deterministic validation agents for order controls, engine controls, and market data stress controls.
- Multi-agent investigation layer with planner, market/order/engine specialists, regulatory mapper, evidence critic, and synthesizer.
- Demo Stack sidebar page for starting the local exchange and AlgoEngine components.
- Investigation Console sidebar page for positive and negative demo cases.
- Validation Evidence sidebar page for direct validation runs.
- How It Works sidebar page explaining one positive and one negative flow.

## What Was Removed

Document-based RTS/PRA loading is no longer part of this TIA build. The project no longer includes:

- `config/rts6_mvp_filter.yaml`
- `config/pra_update_filter.yaml`
- PRA/base regulatory PDFs under `docs/`
- `/knowledge/learn`
- regulatory learning service/model code
- PRA deployment/removal scripts

The runtime still has an in-memory control catalog repository because validation runs need a versioned list of active controls.

## Run UI

```powershell
cd "C:\GAN\Learn\ML & AI\HCL Hackathon  - 2026\Project\TIA"
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app\ui.py
```

## Run API

```powershell
cd "C:\GAN\Learn\ML & AI\HCL Hackathon  - 2026\Project\TIA"
.\.venv\Scripts\python.exe -m uvicorn app:create_api_app --factory --reload --host 127.0.0.1 --port 8602
```

Useful API endpoints:

- `GET /health`
- `GET /agents`
- `GET /knowledge/current` returns the active TIA control catalog.
- `GET /knowledge/versions` returns catalog versions.
- `POST /validations` runs deterministic validation agents.
- `GET /investigations/cases` lists prepared demo cases.
- `POST /investigations` runs the agentic investigation flow.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

