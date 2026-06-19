# AGENTS.md Blueprint Specification

- Product: TIA - Trade Investigative Agents
- Framework: FastAPI + Streamlit
- Runtime Pattern: Fixed MVP control catalog + specialist validation agents + agentic investigation orchestration

## Active Execution Blocks

1. `app/services/compliance_pipeline.py`
   - Initializes the fixed TIA MVP control catalog.
   - Builds the trading gateway, validation registry, and validation service.

2. `app/agents/`
   - Contains deterministic specialist validation agents.
   - Each agent validates one trading control/scenario and returns auditable evidence.

3. `app/investigation_agents/`
   - Contains the agentic investigation layer.
   - Planner chooses investigation path.
   - Market, order, and engine agents call validation tools.
   - Regulatory mapper attaches control context.
   - Evidence critic challenges contradictions.
   - Synthesizer creates the final finding.

4. `app/ui.py`
   - Streamlit demo surface with Investigation Console, Demo Stack, Validation Evidence, and How It Works.

## Out of Scope

- No PRA/RTS/base-document learning.
- No YAML learning filters.
- No runtime generation of new agents from regulation documents.
- No hidden compliance-loader or PRA-updater menu.