from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.services.compliance_pipeline import CompliancePlatform
from app.services.compliance_pipeline import TradingComplianceValidationService
from app.services.process_manager import find_service_process_roots, terminate_process_tree
from app.models.investigation import InvestigationRequest
from app.services.investigation_service import AgenticInvestigationService, DEMO_INVESTIGATION_CASES
from app.agents.registry import ValidationAgentRegistry
from app.trading.algo_engine_gateway import AlgoEngineTcpConfig, AlgoEngineTcpGateway
from app.trading.demo_gateway import DemoTradingSystemGateway
from app.trading.http_gateway import HttpTradingSystemGateway
from app.trading.service import TradingSystemService


st.set_page_config(
    page_title="TIA - Trade Investigative Agents",
    page_icon="",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALL_ENGINE_CONTROLS = 511


def main() -> None:
    st.title("TIA - Trade Investigative Agents")
    st.caption("Agentic investigation for trading controls, market stress, evidence review, and compliance findings.")

    mode = st.sidebar.radio(
        "TIA menu",
        [
            "Trading System Validation",
            "Investigation Demo",
            "Investigative Experience",
            "Demo Stack",
            "Investigation Flow",
            "Agents at Work",
        ],
        index=0,
    )

    if mode == "Investigation Flow":
        render_how_it_works()
        return

    if mode == "Agents at Work":
        render_agents_at_work()
        return

    if mode == "Investigation Demo":
        render_agentic_investigation()
        return

    if mode == "Investigative Experience":
        render_investigative_experience()
        return

    if mode == "Trading System Validation":
        render_validator_mvp()
        return

    if mode == "Demo Stack":
        render_demo_control_center()
        return



def get_demo_platform() -> CompliancePlatform:
    if "compliance_platform" not in st.session_state:
        platform = CompliancePlatform()
        asyncio.run(platform.initialize())
        st.session_state.compliance_platform = platform
    return st.session_state.compliance_platform




def render_investigative_experience() -> None:
    platform = get_demo_platform()
    platform = render_trading_connection_panel(platform)
    service = AgenticInvestigationService(platform)

    st.subheader("Investigative Experience")
    st.write(
        "Choose a guided testcase, tune the scenario inputs, execute the investigation, "
        "and review the final agentic finding with evidence and traceability."
    )

    testcase_options = {
        "Market Data Stress Investigation": {
            "preset": "market_stress_incident",
            "expected": "PASS",
            "default_symbol": "AAPL",
            "default_question": DEMO_INVESTIGATION_CASES["market_stress_incident"]["question"],
        },
        "Pre-Trade Risk Control Investigation": {
            "preset": "pre_trade_risk_control_investigation",
            "expected": "FAIL",
            "default_symbol": "AAPL",
            "default_question": DEMO_INVESTIGATION_CASES["pre_trade_risk_control_investigation"]["question"],
        },
    }

    selected_name = st.selectbox("Testcase", list(testcase_options), key="ix_testcase")
    testcase = testcase_options[selected_name]
    preset = testcase["preset"]

    st.caption("Outcome is driven by the behavior controls below; use them to flip pass/fail deliberately.")

    left, right = st.columns(2)
    with left:
        system_id = st.text_input("Trading system", value="demo-trading-system", key="ix_system_id")
        symbol = st.text_input("Symbol", value=testcase["default_symbol"], key=f"ix_symbol_{preset}").strip().upper() or testcase["default_symbol"]
        dry_run = st.checkbox("Dry run", value=True, key="ix_dry_run")
        evidence_source = st.radio(
            "Evidence source",
            ["Seeded demo evidence", "Active trading connection"],
            index=0,
            key="ix_evidence_source",
            help="Use seeded demo evidence for predictable demo PASS/FAIL. Use active trading connection only when AlgoEngine_TCP is running and healthy.",
        )

    parameters: dict[str, object]
    with right:
        if preset == "market_stress_incident":
            stress_mode = st.selectbox(
                "Market stress mode",
                ["Crossed + locked + one-sided", "Crossed only", "Locked only", "One-sided only"],
                key="ix_stress_mode",
            )
            protection_behavior = st.radio(
                "Market protection behavior",
                ["Protections enabled - expect PASS", "Protections disabled - expect FAIL"],
                horizontal=False,
                key="ix_market_protection_behavior",
            )
            best_bid = st.number_input("Best bid", min_value=0.01, value=175.10, step=0.01, format="%.2f", key="ix_best_bid")
            best_ask = st.number_input("Best ask", min_value=0.01, value=175.00, step=0.01, format="%.2f", key="ix_best_ask")
            market_protections_enabled = protection_behavior.startswith("Protections enabled")
            parameters = {
                "symbol": symbol,
                "market_stress_mode": stress_mode,
                "market_protections_enabled": market_protections_enabled,
                "best_bid": float(best_bid),
                "best_ask": float(best_ask),
                "expected_outcome": "PASS" if market_protections_enabled else "FAIL",
                "operator_intent": "Confirm protections handle stressed market data without creating a breach." if market_protections_enabled else "Confirm disabled protections create detectable market data stress failures.",
                "evidence_source": "demo" if evidence_source == "Seeded demo evidence" else "active_connection",
            }
        else:
            duplicate_behavior = st.radio(
                "Duplicate order behavior",
                ["Reject duplicate - expect PASS", "Accept duplicate - expect FAIL"],
                horizontal=False,
                key="ix_duplicate_behavior",
            )
            bad_price_behavior = st.radio(
                "Bad-price behavior",
                ["Block bad price - expect PASS", "Leak bad price - expect FAIL"],
                horizontal=False,
                key="ix_bad_price_behavior",
            )
            duplicate_order_id = st.text_input("Duplicate client order id", value=f"DUP-{symbol}-001", key="ix_duplicate_id")
            bad_price = st.number_input("Bad price", min_value=0.01, value=210.00, step=0.01, format="%.2f", key="ix_bad_price")
            order_quantity = st.number_input("Order quantity", min_value=1, value=100, step=10, key="ix_order_quantity")
            duplicate_rejected = duplicate_behavior.startswith("Reject duplicate")
            bad_price_blocked = bad_price_behavior.startswith("Block bad price")
            parameters = {
                "symbol": symbol,
                "duplicate_client_order_id": duplicate_order_id,
                "duplicate_rejected": duplicate_rejected,
                "bad_price_blocked": bad_price_blocked,
                "bad_price": float(bad_price),
                "order_quantity": int(order_quantity),
                "expected_outcome": "PASS" if duplicate_rejected and bad_price_blocked else "FAIL",
                "operator_intent": "Confirm duplicate and bad-price protections pass when controls block unsafe behavior." if duplicate_rejected and bad_price_blocked else "Confirm pre-trade risk control failures are detected from evidence.",
                "evidence_source": "demo" if evidence_source == "Seeded demo evidence" else "active_connection",
            }

    question_seed = testcase["default_question"]
    question = st.text_area(
        "Investigation question",
        value=f"{question_seed}\n\nUser-selected scenario parameters: {json.dumps(parameters, sort_keys=True)}",
        height=120,
        key=f"ix_question_{preset}",
    )

    with st.expander("Scenario setup preview", expanded=True):
        st.json(parameters)
        st.info(f"Expected outcome from selected behavior: {parameters.get('expected_outcome', 'UNKNOWN')}")
        st.write("Agent path will be selected by the planner from the testcase preset and investigation question.")

    if st.button("Execute Testcase", type="primary", use_container_width=True, key="ix_execute"):
        request = InvestigationRequest(
            system_id=system_id,
            question=question,
            preset=preset,
            dry_run=dry_run,
            parameters=parameters,
        )
        with st.spinner("Executing testcase through TIA investigation agents..."):
            finding = asyncio.run(service.investigate(request))
        st.session_state.ix_last_finding = finding
        st.session_state.ix_last_testcase = selected_name
        st.session_state.ix_last_parameters = parameters

    finding = st.session_state.get("ix_last_finding")
    if not finding:
        st.info("Select a testcase, adjust parameters, and press Execute Testcase.")
        return

    st.divider()
    st.caption(f"Last executed testcase: {st.session_state.get('ix_last_testcase', selected_name)}")
    render_investigation_result(finding)


def validation_status_label(status: str) -> str:
    labels = {
        "pass": "PASS - control behaved as expected",
        "fail": "FAIL - breach evidence found",
        "review": "REVIEW - evidence incomplete",
    }
    return labels.get(status, status.upper())


def validation_severity(status: str) -> str:
    severities = {
        "pass": "OK",
        "fail": "High",
        "review": "Medium",
    }
    return severities.get(status, "Unknown")


def compact_text(value: object, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def evidence_sources(item) -> str:
    sources = []
    for evidence in item.evidence:
        source = getattr(evidence, "source", "")
        if source and source not in sources:
            sources.append(source)
    return ", ".join(sources) or "Not captured"


def evidence_snapshot(item) -> str:
    descriptions = [
        getattr(evidence, "description", "")
        for evidence in item.evidence
        if getattr(evidence, "description", "")
    ]
    if descriptions:
        return compact_text(" | ".join(descriptions), 220)
    return compact_text(item.observed_behavior, 220)


def render_validation_evidence_table(validation_results, title: str = "Evidence Result") -> None:
    st.markdown(f"### {title}")
    if not validation_results:
        st.info("No validation evidence was produced for this investigation.")
        return

    counts = Counter(item.status.value for item in validation_results)
    pass_col, fail_col, review_col, evidence_col = st.columns(4)
    pass_col.metric("Passed", counts.get("pass", 0))
    fail_col.metric("Failed", counts.get("fail", 0))
    review_col.metric("Needs review", counts.get("review", 0))
    evidence_col.metric("Evidence items", sum(len(item.evidence) for item in validation_results))

    rows = []
    for item in validation_results:
        status = item.status.value
        rows.append(
            {
                "Status": validation_status_label(status),
                "Severity": validation_severity(status),
                "Control": f"{item.control_id} - {item.control_name}",
                "Agent": item.agent_name.replace("-", " "),
                "Finding": compact_text(item.observed_behavior, 140),
                "Reason": ", ".join(item.reason_codes) or "No reason code",
                "Evidence": evidence_snapshot(item),
                "Confidence": f"{item.confidence:.0%}",
            }
        )

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Finding": st.column_config.TextColumn("Finding", width="large"),
            "Evidence": st.column_config.TextColumn("Evidence", width="large"),
            "Control": st.column_config.TextColumn("Control", width="medium"),
            "Confidence": st.column_config.TextColumn("Confidence", width="small"),
        },
    )

    with st.expander("Control-by-control evidence details", expanded=False):
        for item in validation_results:
            status = item.status.value
            st.markdown(f"**{validation_status_label(status)} | {item.control_id} - {item.control_name}**")
            st.write(f"Agent: {item.agent_name}")
            st.write(f"Expected: {item.expected_behavior}")
            st.write(f"Observed: {item.observed_behavior}")
            if item.reason_codes:
                st.write(f"Reason codes: {', '.join(item.reason_codes)}")
            st.write(f"Evidence source: {evidence_sources(item)}")
            if item.evidence:
                evidence_rows = []
                for evidence in item.evidence:
                    evidence_rows.append(
                        {
                            "type": evidence.evidence_type,
                            "source": evidence.source,
                            "observed_at": evidence.observed_at.isoformat(),
                            "description": evidence.description,
                            "value": compact_text(evidence.value, 260),
                        }
                    )
                st.dataframe(pd.DataFrame(evidence_rows), hide_index=True, use_container_width=True)
            if item.remediation:
                st.write("Remediation:")
                for action in item.remediation:
                    st.write(f"- {action}")
            if item.citations:
                st.write(f"Citations: {', '.join(item.citations)}")
            st.divider()


def render_investigation_result(finding) -> None:
    left, middle, right = st.columns(3)
    left.metric("Final status", finding.final_status.value.upper())
    middle.metric("Confidence", f"{finding.confidence:.0%}")
    right.metric("Failed controls", len(finding.failed_controls))

    if finding.final_status.value == "pass":
        st.success(finding.conclusion)
    elif finding.final_status.value == "fail":
        st.error(finding.conclusion)
    else:
        st.warning(finding.conclusion)

    st.write(f"**Root cause:** {finding.root_cause}")
    st.markdown("### Why This Result")
    why = investigation_result_summary(finding)
    if finding.final_status.value == "pass":
        st.success(why)
    elif finding.final_status.value == "fail":
        st.error(why)
    else:
        st.warning(why)

    if finding.regulatory_mapping.get("request_parameters"):
        with st.expander("Executed parameters", expanded=False):
            st.json(finding.regulatory_mapping["request_parameters"])

    render_validation_evidence_table(finding.validation_results, "Evidence Result")

    st.markdown("### Agent Trace")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "agent": step.agent_name,
                    "action": step.action,
                    "decision": step.decision,
                    "controls": ", ".join(step.selected_controls),
                    "next": step.next_step,
                }
                for step in finding.agent_trace
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    if finding.recommended_actions:
        st.markdown("### Recommended Actions")
        for action in finding.recommended_actions:
            st.write(f"- {action}")

    confidence_factors = finding.regulatory_mapping.get("confidence_factors", [])
    if confidence_factors:
        with st.expander("Confidence calculation", expanded=False):
            for factor in confidence_factors:
                st.write(f"- {factor}")

    with st.expander("Raw investigation JSON"):
        st.json(finding.model_dump(mode="json"))


def investigation_result_summary(finding) -> str:
    parameters = finding.regulatory_mapping.get("request_parameters", {}) if finding.regulatory_mapping else {}
    failed = [item for item in finding.validation_results if item.status.value == "fail"]
    review = [item for item in finding.validation_results if item.status.value == "review"]
    passed = [item for item in finding.validation_results if item.status.value == "pass"]
    expected = parameters.get("expected_outcome")
    expected_text = f" Selected setup expected {expected}." if expected else ""

    if failed:
        failed_controls = ", ".join(f"{item.control_id} {item.control_name}" for item in failed[:4])
        reason_codes = sorted({code for item in failed for code in item.reason_codes})
        reason_text = ", ".join(reason_codes[:6]) or "control failure evidence"
        return (
            f"FAIL because {len(failed)} control(s) produced breach evidence: {failed_controls}. "
            f"Primary reason codes: {reason_text}.{expected_text}"
        )

    if review:
        review_controls = ", ".join(f"{item.control_id} {item.control_name}" for item in review[:4])
        return (
            f"REVIEW because {len(review)} control(s) need additional evidence or specialist coverage: "
            f"{review_controls}.{expected_text}"
        )

    if passed:
        controls = ", ".join(item.control_id for item in passed[:6])
        return (
            f"PASS because all {len(passed)} executed controls matched expected protective behavior. "
            f"Validated controls include {controls}.{expected_text}"
        )

    return "No validation evidence was produced for this investigation."

def render_how_it_works() -> None:
    st.subheader("Investigation Flow")
    st.write(
        "This page is the operating map for TIA. It shows what the user sets up, what the agents do, "
        "where evidence is gathered, and how the final pass/fail finding is produced."
    )

    st.markdown(
        """
<style>
.tia-flow-step {border:1px solid #D0D5DD; border-radius:8px; padding:12px 14px; margin:6px 0; background:#FFFFFF;}
.tia-flow-title {font-weight:700; color:#101828; margin-bottom:4px;}
.tia-flow-copy {color:#475467; font-size:0.94rem; line-height:1.35;}
.tia-arrow {text-align:center; color:#667085; font-weight:700; padding:2px 0;}
.tia-pass {border-left:5px solid #12B76A;}
.tia-fail {border-left:5px solid #F04438;}
.tia-neutral {border-left:5px solid #2E90FA;}
</style>
        """,
        unsafe_allow_html=True,
    )

    def flow_step(title: str, copy: str, tone: str = "neutral") -> None:
        st.markdown(
            f"""
<div class="tia-flow-step tia-{tone}">
  <div class="tia-flow-title">{title}</div>
  <div class="tia-flow-copy">{copy}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

    def arrow() -> None:
        st.markdown('<div class="tia-arrow">↓</div>', unsafe_allow_html=True)

    st.markdown("### Overall Flow")
    flow_step("1. Demo Stack", "Start or use the demo trading gateway, exchange simulator, market-data path, admin path, and query path.")
    arrow()
    flow_step("2. User Chooses Testcase", "In Investigative Experience, the user picks either Market Data Stress Investigation or Pre-Trade Risk Control Investigation.")
    arrow()
    flow_step("3. User Selects Behavior", "The user chooses whether protections are enabled/disabled, or whether duplicate/bad-price controls block or leak unsafe behavior.")
    arrow()
    flow_step("4. Planner Agent", "The planner reads the testcase and question, then chooses the first investigation path: market-first or order-first.")
    arrow()
    flow_step("5. Specialist Investigation Agents", "Market, order, and engine agents call deterministic validation tools for the relevant controls.")
    arrow()
    flow_step("6. Evidence + Control Results", "Each validation agent returns pass/fail/review, evidence, reason codes, confidence, and remediation.")
    arrow()
    flow_step("7. Regulatory Mapping Agent", "The results are mapped back to the active TIA control catalog and citations for traceability.")
    arrow()
    flow_step("8. Evidence Critic Agent", "The critic checks whether failures are supported and whether the evidence contradicts itself.")
    arrow()
    flow_step("9. Decision Synthesizer", "The synthesizer produces final status, confidence, root cause, why-result summary, and recommended actions.")

    st.divider()
    st.markdown("### Testcase A: Market-Stress Protection")
    st.caption("This path proves that a normally passing Market Data Stress Investigation testcase can be made to fail by disabling protections.")

    left, right = st.columns(2)
    with left:
        st.markdown("#### PASS Path")
        flow_step("Input", "Symbol AAPL; crossed/locked/one-sided stress; market protections enabled.", "pass")
        arrow()
        flow_step("Market Agent", "Runs STRESS-001, STRESS-002, STRESS-003 against protected market behavior.", "pass")
        arrow()
        flow_step("Evidence", "Crossed market is normalized/restricted, locked market orders are held/cancelled, one-sided market order does not leak.", "pass")
        arrow()
        flow_step("Outcome", "PASS because market protections handled stressed market data as expected.", "pass")
    with right:
        st.markdown("#### FAIL Path")
        flow_step("Input", "Symbol AAPL; crossed/locked/one-sided stress; market protections disabled.", "fail")
        arrow()
        flow_step("Market Agent", "Runs the same STRESS controls, but receives failure evidence from the scenario behavior override.", "fail")
        arrow()
        flow_step("Evidence", "Crossed market remains unsafe, locked market is not restricted, one-sided order reaches exchange.", "fail")
        arrow()
        flow_step("Outcome", "FAIL because STRESS controls produce breach evidence and reason codes.", "fail")

    st.markdown("#### Market-Stress Agent Route")
    st.code(
        "User parameters -> Planner -> Market Investigation Agent -> Engine Control Agent -> Regulatory Mapping -> Evidence Critic -> Decision Synthesizer -> Why This Result",
        language="text",
    )

    st.divider()
    st.markdown("### Testcase B: Order-Control Breach")
    st.caption("This path proves that a normally failing Pre-Trade Risk Control Investigation testcase can be made to pass when controls block unsafe behavior.")

    left, right = st.columns(2)
    with left:
        st.markdown("#### PASS Path")
        flow_step("Input", "Duplicate rejected and bad price blocked.", "pass")
        arrow()
        flow_step("Order Agent", "Runs CTRL-001, CTRL-002, CTRL-003, and CTRL-006.", "pass")
        arrow()
        flow_step("Evidence", "Duplicate receives reject; bad-price order is rejected/halted; market order conversion and parent-child checks pass.", "pass")
        arrow()
        flow_step("Outcome", "PASS because all executed order and engine controls match expected behavior.", "pass")
    with right:
        st.markdown("#### FAIL Path")
        flow_step("Input", "Duplicate accepted and/or bad price leaks to exchange.", "fail")
        arrow()
        flow_step("Order Agent", "Runs the same order controls, but scenario behavior creates breach evidence.", "fail")
        arrow()
        flow_step("Evidence", "Duplicate order is accepted twice, or bad-price order is accepted/leaked rather than blocked.", "fail")
        arrow()
        flow_step("Outcome", "FAIL because CTRL-002 and/or CTRL-003 return failure reason codes.", "fail")

    st.markdown("#### Order-Control Agent Route")
    st.code(
        "User parameters -> Planner -> Order Investigation Agent -> Engine Control Agent -> Regulatory Mapping -> Evidence Critic -> Decision Synthesizer -> Why This Result",
        language="text",
    )

    st.divider()
    st.markdown("### What The User Sees After Execute Testcase")
    result_rows = [
        {"UI section": "Final status", "Meaning": "PASS, FAIL, or REVIEW from synthesized evidence."},
        {"UI section": "Why This Result", "Meaning": "Plain-language reason using failed controls, reason codes, and selected expected outcome."},
        {"UI section": "Executed parameters", "Meaning": "The exact behavior choices the user selected before execution."},
        {"UI section": "Evidence Result", "Meaning": "Control-by-control validation results, agents, status, reason codes, confidence."},
        {"UI section": "Agent Trace", "Meaning": "Which agent acted, what it decided, what controls it selected, and where it handed off next."},
        {"UI section": "Recommended Actions", "Meaning": "Remediation guidance if controls fail, or audit-retention guidance if they pass."},
    ]
    st.dataframe(pd.DataFrame(result_rows), hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("### Decision Logic")
    flow_step("If any executed control FAILS", "Final status is FAIL. The result explains failed controls and reason codes.", "fail")
    arrow()
    flow_step("If no controls fail but evidence is incomplete", "Final status is REVIEW. The user should collect evidence or add missing specialist coverage.", "neutral")
    arrow()
    flow_step("If all executed controls pass", "Final status is PASS. TIA records evidence, agent trace, confidence factors, and audit-ready result.", "pass")

    st.divider()
    with st.expander("Why This Is Agentic", expanded=True):
        st.write(
            "TIA is not only running a static checklist. The planner chooses a route, specialist agents call validation tools, "
            "the critic challenges the evidence, and the synthesizer decides the final finding from the collected trace. "
            "The user can change behavior inputs and force the investigation down a pass or fail path."
        )
def render_agentic_investigation() -> None:
    platform = get_demo_platform()
    platform = render_trading_connection_panel(platform)
    service = AgenticInvestigationService(platform)

    st.subheader("Investigation Demo")
    st.write(
        "Runs a multi-agent investigation over a trading incident. The agentic layer plans a path, "
        "calls deterministic validation agents as tools, checks regulatory mapping, challenges the evidence, "
        "and produces a final compliance finding."
    )

    case_labels = {key: value["name"] for key, value in DEMO_INVESTIGATION_CASES.items()}
    selected_label = st.selectbox("Demo testcase", list(case_labels.values()), key="investigation_case_label")
    selected_case = next(key for key, label in case_labels.items() if label == selected_label)
    if st.session_state.get("active_investigation_case") != selected_case:
        st.session_state.active_investigation_case = selected_case
        st.session_state.pop("last_investigation_finding", None)
        st.session_state.pop("last_investigation_case", None)
    case = DEMO_INVESTIGATION_CASES[selected_case]

    st.markdown("### Prepared Demo Data")
    st.write(case["question"])
    st.dataframe(
        pd.DataFrame(
            [
                {"step": index + 1, "data_preparation": item}
                for index, item in enumerate(case["data_preparation"])
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("Why this is agentic", expanded=True):
        st.write(
            "The investigation does not simply run a static report. The planner chooses a first path based on the case, "
            "specialist investigation agents run selected control tools, the evidence critic checks contradictions, "
            "and the synthesizer decides the final outcome."
        )

    question = st.text_area("Investigation question", value=case["question"], height=90)
    system_id = st.text_input("System id", value="demo-trading-system", key="investigation_system_id")
    dry_run = st.checkbox("Dry run", value=True, key="investigation_dry_run")

    run_clicked = st.button(
        "Run TIA Investigation",
        type="primary",
        use_container_width=True,
        key=f"run_agentic_investigation_{selected_case}",
    )
    if run_clicked:
        request = InvestigationRequest(system_id=system_id, question=question, preset=selected_case, dry_run=dry_run)
        finding = asyncio.run(service.investigate(request))
        st.session_state.last_investigation_finding = finding
        st.session_state.last_investigation_case = selected_case

    finding = st.session_state.get("last_investigation_finding")
    if not finding or st.session_state.get("last_investigation_case") != selected_case:
        st.info("Select a testcase and run the TIA investigation to generate a fresh finding.")
        return

    st.caption(f"Showing result for: {case['name']}")

    left, middle, right = st.columns(3)
    left.metric("Final status", finding.final_status.value.upper())
    middle.metric("Confidence", f"{finding.confidence:.0%}")
    right.metric("Human review", "Yes" if finding.human_review_required else "No")

    st.markdown("### Final Finding")
    st.success(finding.conclusion) if finding.final_status.value == "pass" else st.warning(finding.conclusion)
    st.write(f"**Root cause:** {finding.root_cause}")
    st.markdown("### Why This Result")
    why = investigation_result_summary(finding)
    if finding.final_status.value == "pass":
        st.success(why)
    elif finding.final_status.value == "fail":
        st.error(why)
    else:
        st.warning(why)
    confidence_factors = finding.regulatory_mapping.get("confidence_factors", []) if finding.regulatory_mapping else []
    if confidence_factors:
        with st.expander("Confidence calculation", expanded=False):
            for factor in confidence_factors:
                st.write(f"- {factor}")

    st.markdown("### Agent Trace")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "agent": step.agent_name,
                    "action": step.action,
                    "decision": step.decision,
                    "controls": ", ".join(step.selected_controls),
                    "next": step.next_step,
                }
                for step in finding.agent_trace
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    render_validation_evidence_table(finding.validation_results, "Validation Evidence Used")

    if finding.contradictions:
        st.markdown("### Evidence Critic Findings")
        st.error("\n".join(finding.contradictions))

    st.markdown("### Recommended Actions")
    for action in finding.recommended_actions:
        st.write(f"- {action}")

    with st.expander("Raw investigation JSON"):
        st.json(finding.model_dump(mode="json"))

def render_demo_control_center() -> None:
    platform = get_demo_platform()

    st.subheader("Demo Stack")
    st.write(
        "Start the local demo stack, verify health, and switch validation to the live AlgoEngine TCP gateway."
    )

    with st.expander("Demo stack ports", expanded=True):
        host_col, exchange_col, query_col = st.columns(3)
        host = host_col.text_input("Host", value=st.session_state.get("demo_stack_host", "127.0.0.1"))
        exchange_port = exchange_col.number_input("Exchange Simulator port", min_value=1, max_value=65535, value=int(st.session_state.get("demo_exchange_port", 9601)), step=1)
        query_port = query_col.number_input("Exchange Simulator query port", min_value=1, max_value=65535, value=int(st.session_state.get("demo_exchange_query_port", 9602)), step=1)

        client_col, market_col, admin_col = st.columns(3)
        client_port = client_col.number_input("AlgoEngine client port", min_value=1, max_value=65535, value=int(st.session_state.get("demo_client_port", 9500)), step=1)
        market_data_port = market_col.number_input("AlgoEngine market data port", min_value=1, max_value=65535, value=int(st.session_state.get("demo_market_data_port", 9501)), step=1)
        admin_port = admin_col.number_input("AlgoEngine admin port", min_value=1, max_value=65535, value=int(st.session_state.get("demo_admin_port", 9502)), step=1)

    st.session_state.demo_stack_host = host
    st.session_state.demo_exchange_port = int(exchange_port)
    st.session_state.demo_exchange_query_port = int(query_port)
    st.session_state.demo_client_port = int(client_port)
    st.session_state.demo_market_data_port = int(market_data_port)
    st.session_state.demo_admin_port = int(admin_port)

    start_col, health_col, stop_col = st.columns(3)
    if start_col.button("Start Full Demo Stack", type="primary", use_container_width=True):
        start_full_demo_stack(host, int(exchange_port), int(query_port), int(client_port), int(market_data_port), int(admin_port), platform)

    if health_col.button("Health Check", use_container_width=True):
        run_demo_stack_health_check(host, int(exchange_port), int(query_port), int(client_port), int(market_data_port), int(admin_port), platform)

    if stop_col.button("Stop Full Demo Stack", use_container_width=True):
        stop_full_demo_stack(
            int(client_port),
            int(market_data_port),
            int(admin_port),
            int(exchange_port),
            int(query_port),
        )

    log_text = "\n".join(st.session_state.get("demo_stack_log", ["$ waiting for demo stack action..."]))
    st.text_area("Demo stack status", value=log_text, height=300, disabled=True)

    if st.session_state.get("demo_stack_ready"):
        st.success("Ready for execution")
    else:
        st.warning("Demo stack is not ready yet.")

    st.divider()
    st.markdown("### Execute")
    if st.button("Run Full Validation", type="primary", use_container_width=True, disabled=not st.session_state.get("demo_stack_ready")):
        active_platform = st.session_state.get("compliance_platform", platform)
        run = asyncio.run(active_platform.validator.validate_system("demo-trading-system", dry_run=True))
        status_counts = Counter(item.status.value for item in run.results)
        st.success(f"Validation complete: {run.overall_status.value.upper()}")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "control_id": item.control_id,
                        "control_name": item.control_name,
                        "agent": item.agent_name,
                        "status": item.status.value,
                        "reason_codes": ", ".join(item.reason_codes),
                    }
                    for item in run.results
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.bar_chart(pd.DataFrame(status_counts.items(), columns=["status", "count"]), x="status", y="count")
        with st.expander("Raw validation evidence"):
            payload = run.model_dump(mode="json")
            payload["overall_status"] = run.overall_status.value
            st.json(payload)


def reset_demo_stack_log() -> None:
    st.session_state.demo_stack_log = []
    st.session_state.demo_stack_ready = False


def append_demo_stack_log(message: str) -> None:
    lines = st.session_state.get("demo_stack_log", [])
    lines.append(message)
    st.session_state.demo_stack_log = lines[-80:]


def process_is_running(process) -> bool:
    return process is not None and process.poll() is None


def start_full_demo_stack(host: str, exchange_port: int, query_port: int, client_port: int, market_data_port: int, admin_port: int, platform: CompliancePlatform) -> None:
    reset_demo_stack_log()
    append_demo_stack_log("$ demo-stack up")
    append_demo_stack_log(f"[INFO] project root: {PROJECT_ROOT}")

    if not process_is_running(st.session_state.get("dummy_exchange_process")):
        if port_is_open(host, exchange_port) and port_is_open(host, query_port):
            append_demo_stack_log(f"[OK] Exchange Simulator already reachable on {host}:{exchange_port}/{query_port}")
        else:
            command = [
                sys.executable,
                "-m",
                "AlgoEngine.dummy_exchange",
                "--host",
                host,
                "--port",
                str(exchange_port),
                "--query-port",
                str(query_port),
            ]
            st.session_state.dummy_exchange_process = start_background_process(command)
            append_demo_stack_log(f"[START] Exchange Simulator pid={st.session_state.dummy_exchange_process.pid}")
    else:
        append_demo_stack_log(f"[OK] Exchange Simulator already running pid={st.session_state.dummy_exchange_process.pid}")

    wait_for_port(host, exchange_port, "Exchange Simulator FIX port")
    wait_for_port(host, query_port, "Exchange Simulator query port")

    if not process_is_running(st.session_state.get("algoengine_process")):
        if port_is_open(host, client_port) and port_is_open(host, admin_port):
            append_demo_stack_log(f"[OK] AlgoEngine already reachable on {host}:{client_port}/{admin_port}")
        else:
            command = [
                sys.executable,
                "-m",
                "AlgoEngine.local_engine",
                "--host",
                host,
                "--client-port",
                str(client_port),
                "--market-data-port",
                str(market_data_port),
                "--admin-port",
                str(admin_port),
                "--exchange-host",
                host,
                "--exchange-port",
                str(exchange_port),
                "--controls",
                str(ALL_ENGINE_CONTROLS),
            ]
            st.session_state.algoengine_process = start_background_process(command)
            append_demo_stack_log(f"[START] AlgoEngine local_engine pid={st.session_state.algoengine_process.pid}")
    else:
        append_demo_stack_log(f"[OK] AlgoEngine already running pid={st.session_state.algoengine_process.pid}")

    wait_for_port(host, client_port, "AlgoEngine client order port")
    wait_for_port(host, market_data_port, "AlgoEngine market data port")
    wait_for_port(host, admin_port, "AlgoEngine admin port")

    run_demo_stack_health_check(host, exchange_port, query_port, client_port, market_data_port, admin_port, platform, reset_log=False)


def start_background_process(command: list[str]) -> subprocess.Popen:
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def wait_for_port(host: str, port: int, label: str, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if port_is_open(host, port):
            return True
        time.sleep(0.25)
    append_demo_stack_log(f"[FAIL] {label} not reachable at {host}:{port}")
    return False


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def run_demo_stack_health_check(host: str, exchange_port: int, query_port: int, client_port: int, market_data_port: int, admin_port: int, platform: CompliancePlatform, reset_log: bool = True) -> None:
    if reset_log:
        reset_demo_stack_log()
        append_demo_stack_log("$ demo-stack health-check")

    checks: list[bool] = []
    checks.append(check_port(host, exchange_port, "Exchange Simulator FIX port"))
    checks.append(check_port(host, query_port, "Exchange Simulator query port"))
    checks.append(check_port(host, client_port, "AlgoEngine client order port"))
    checks.append(check_port(host, market_data_port, "AlgoEngine market data port"))
    checks.append(check_port(host, admin_port, "AlgoEngine admin port"))

    exchange_status = query_dummy_exchange_status(host, query_port)
    checks.append(exchange_status is not None)
    if exchange_status is not None:
        append_demo_stack_log(f"[OK] Exchange Simulator query responded: total_received={exchange_status.get('total_received', 0)} captured={exchange_status.get('captured', 0)}")

    engine_status = query_algoengine_status(host, admin_port)
    checks.append(engine_status is not None and engine_status.get("status") in {"running", "halted"})
    if engine_status is not None:
        append_demo_stack_log(f"[OK] AlgoEngine admin responded: status={engine_status.get('status')} controls={ALL_ENGINE_CONTROLS}")

    knowledge = asyncio.run(platform.knowledge_base.current())
    checks.append(len(knowledge.controls) >= 9)
    append_demo_stack_log(f"[OK] Catalog Version={knowledge.version} controls={len(knowledge.controls)}" if len(knowledge.controls) >= 9 else f"[FAIL] knowledge controls={len(knowledge.controls)} expected>=9")

    if all(checks):
        configure_demo_stack_gateway(host, query_port, client_port, market_data_port, admin_port, platform)
        st.session_state.demo_stack_ready = True
        append_demo_stack_log("[READY] all demo stack checks passed")
    else:
        st.session_state.demo_stack_ready = False
        append_demo_stack_log("[NOT READY] one or more checks failed")


def check_port(host: str, port: int, label: str) -> bool:
    ok = port_is_open(host, port)
    append_demo_stack_log(f"[OK] {label} reachable at {host}:{port}" if ok else f"[FAIL] {label} not reachable at {host}:{port}")
    return ok


def query_dummy_exchange_status(host: str, query_port: int) -> dict | None:
    try:
        with socket.create_connection((host, query_port), timeout=3) as connection:
            connection.settimeout(3)
            connection.sendall(b"GET STATUS\n")
            response = connection.recv(65536).decode("utf-8", errors="replace").strip()
        return json.loads(response)
    except (OSError, json.JSONDecodeError) as exc:
        append_demo_stack_log(f"[FAIL] Exchange Simulator query failed: {exc}")
        return None


def query_algoengine_status(host: str, admin_port: int) -> dict | None:
    try:
        with socket.create_connection((host, admin_port), timeout=3) as connection:
            connection.settimeout(3)
            connection.recv(65536)
            connection.sendall(b"STATUS\n")
            response = connection.recv(65536).decode("utf-8", errors="replace").strip()
        return json.loads(response)
    except (OSError, json.JSONDecodeError) as exc:
        append_demo_stack_log(f"[FAIL] AlgoEngine admin status failed: {exc}")
        return None


def configure_demo_stack_gateway(host: str, query_port: int, client_port: int, market_data_port: int, admin_port: int, platform: CompliancePlatform) -> None:
    settings = {
        "gateway_type": "algoengine_tcp",
        "protocol": "http",
        "host": host,
        "port": 8080,
        "client_port": int(client_port),
        "market_data_port": int(market_data_port),
        "admin_port": int(admin_port),
        "exchange_host": host,
        "exchange_query_port": int(query_port),
        "api_token": "",
        "verify_tls": True,
        "timeout": 5.0,
    }
    st.session_state.trading_gateway_type = "algoengine_tcp"
    st.session_state.trading_host = host
    st.session_state.algoengine_client_port = int(client_port)
    st.session_state.algoengine_market_data_port = int(market_data_port)
    st.session_state.algoengine_admin_port = int(admin_port)
    st.session_state.dummy_exchange_host = host
    st.session_state.dummy_exchange_query_port = int(query_port)
    st.session_state.trading_connection_settings = settings
    st.session_state.compliance_platform = rebuild_platform_for_connection(settings, platform)
    append_demo_stack_log("[OK] validation gateway set to algoengine_tcp")


def stop_full_demo_stack(client_port: int, market_data_port: int, admin_port: int, exchange_port: int, query_port: int) -> None:
    reset_demo_stack_log()
    append_demo_stack_log("$ demo-stack down")
    stop_service_process(
        "algoengine_process",
        "AlgoEngine local_engine",
        "AlgoEngine.local_engine",
        (client_port, market_data_port, admin_port),
    )
    stop_service_process(
        "dummy_exchange_process",
        "Exchange Simulator",
        "AlgoEngine.dummy_exchange",
        (exchange_port, query_port),
    )
    st.session_state.demo_stack_ready = False
    append_demo_stack_log("[OK] stop sequence completed")


def stop_service_process(key: str, label: str, module_name: str, ports: tuple[int, ...]) -> None:
    stopped_pids: set[int] = set()
    process = st.session_state.get(key)
    if process is not None and process.poll() is None:
        try:
            terminated = terminate_process_tree(process.pid)
            stopped_pids.update(terminated)
            append_demo_stack_log(f"[OK] stopped tracked {label} process tree pids={terminated}")
        except Exception as exc:
            append_demo_stack_log(f"[FAIL] could not stop tracked {label}: {exc}")
    elif process is not None:
        append_demo_stack_log(f"[OK] {label} already stopped rc={process.returncode}")
    st.session_state.pop(key, None)

    try:
        recovered_pids = find_service_process_roots(ports, module_name, PROJECT_ROOT)
    except Exception as exc:
        append_demo_stack_log(f"[FAIL] could not inspect configured ports for {label}: {exc}")
        return

    for pid in recovered_pids:
        if pid in stopped_pids:
            continue
        try:
            terminated = terminate_process_tree(pid)
            stopped_pids.update(terminated)
            append_demo_stack_log(f"[OK] stopped recovered {label} process tree pids={terminated}")
        except Exception as exc:
            append_demo_stack_log(f"[FAIL] could not stop recovered {label} pid={pid}: {exc}")

    if not stopped_pids:
        append_demo_stack_log(f"[SKIP] no matching TIA {label} process found on ports={list(ports)}")


def render_validator_mvp() -> None:
    platform = get_demo_platform()

    st.subheader("Trading System Validation")
    st.write(
        "Run deterministic validation evidence checks against the current TIA Catalog Version."
    )

    tabs = st.tabs(
        [
            "1 Validation Run",
        ]
    )

    with tabs[0]:
        render_validation_runner(platform)


def render_validation_runner(platform: CompliancePlatform) -> None:
    platform = render_trading_connection_panel(platform)

    st.markdown("### Run Trading-System Validation")
    system_id = st.text_input(
        "Trading system ID",
        value=st.session_state.get("trading_system_id", "demo-trading-system"),
    )
    st.session_state.trading_system_id = system_id
    dry_run = st.checkbox("Dry run", value=True)
    knowledge_version = st.text_input(
        "Control catalog version override",
        value="",
        help="Leave blank to use the current Catalog Version.",
    )

    if st.button("Run Validation", type="primary", use_container_width=True):
        with st.spinner("Running validation agents against trading-system gateway..."):
            run = asyncio.run(
                platform.validator.validate_system(
                    system_id=system_id,
                    knowledge_version=knowledge_version.strip() or None,
                    dry_run=dry_run,
                )
            )

        status_counts = Counter(item.status.value for item in run.results)
        left, middle, right = st.columns(3)
        left.metric("Overall Status", run.overall_status.value.upper())
        middle.metric("Catalog Version", run.knowledge_version)
        right.metric("Results", len(run.results))

        st.bar_chart(
            pd.DataFrame(status_counts.items(), columns=["status", "count"]),
            x="status",
            y="count",
        )

        rows = []
        for result in run.results:
            rows.append(
                {
                    "control_id": result.control_id,
                    "control_name": result.control_name,
                    "agent": result.agent_name,
                    "status": result.status.value,
                    "reason_codes": ", ".join(result.reason_codes),
                    "remediation": "; ".join(result.remediation),
                    "citations": "; ".join(result.citations),
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        with st.expander("Raw validation JSON"):
            payload = run.model_dump(mode="json")
            payload["overall_status"] = run.overall_status.value
            st.json(payload)


def render_trading_connection_panel(platform: CompliancePlatform) -> CompliancePlatform:
    st.markdown("### Trading System Connection")
    with st.expander("Connection settings", expanded=True):
        left, middle, right = st.columns([1.1, 1.4, 1])
        gateway_options = ["demo", "algoengine_tcp"]
        gateway_labels = {"demo": "demo", "algoengine_tcp": "AlgoEngine_TCP"}
        current_gateway = st.session_state.get("trading_gateway_type", "demo")
        gateway_index = gateway_options.index(current_gateway) if current_gateway in gateway_options else 0
        gateway_type = left.selectbox(
            "Gateway",
            gateway_options,
            index=gateway_index,
            format_func=lambda option: gateway_labels.get(option, option),
        )
        protocol = middle.selectbox(
            "Protocol",
            ["http", "https"],
            index=0 if st.session_state.get("trading_protocol", "http") == "http" else 1,
            disabled=gateway_type != "http",
        )
        verify_tls = right.checkbox(
            "Verify TLS",
            value=st.session_state.get("trading_verify_tls", True),
            disabled=gateway_type != "http" or protocol == "http",
        )

        api_token = ""
        port = int(st.session_state.get("trading_port", 8080))
        client_port = int(st.session_state.get("algoengine_client_port", 9500))
        market_data_port = int(st.session_state.get("algoengine_market_data_port", 9501))
        admin_port = int(st.session_state.get("algoengine_admin_port", 9502))
        exchange_host = st.session_state.get("dummy_exchange_host", st.session_state.get("trading_host", "127.0.0.1"))
        exchange_query_port = int(st.session_state.get("dummy_exchange_query_port", 9602))

        host_col, timeout_col = st.columns([2, 1])
        host = host_col.text_input(
            "Host/IP",
            value=st.session_state.get("trading_host", "127.0.0.1"),
            disabled=gateway_type == "demo",
            help="For AlgoEngine, this is the IP where local_engine is listening.",
        )
        timeout = timeout_col.number_input(
            "Timeout sec",
            min_value=1.0,
            max_value=120.0,
            value=float(st.session_state.get("trading_timeout", 25.0)),
            step=1.0,
            disabled=gateway_type == "demo",
        )

        if gateway_type == "http":
            port_col, token_col = st.columns([1, 2])
            port = port_col.number_input(
                "HTTP port",
                min_value=1,
                max_value=65535,
                value=int(st.session_state.get("trading_port", 8080)),
                step=1,
            )
            api_token = token_col.text_input(
                "Bearer token",
                value=st.session_state.get("trading_api_token", ""),
                type="password",
            )

        if gateway_type == "algoengine_tcp":
            client_col, market_col, admin_col = st.columns(3)
            client_port = client_col.number_input(
                "Client order port",
                min_value=1,
                max_value=65535,
                value=int(st.session_state.get("algoengine_client_port", 9500)),
                step=1,
            )
            market_data_port = market_col.number_input(
                "Market data port",
                min_value=1,
                max_value=65535,
                value=int(st.session_state.get("algoengine_market_data_port", 9501)),
                step=1,
            )
            admin_port = admin_col.number_input(
                "Admin port",
                min_value=1,
                max_value=65535,
                value=int(st.session_state.get("algoengine_admin_port", 9502)),
                step=1,
            )
            exchange_host_col, exchange_port_col = st.columns(2)
            exchange_host = exchange_host_col.text_input(
                "Exchange host/IP",
                value=st.session_state.get("dummy_exchange_host", st.session_state.get("trading_host", "127.0.0.1")),
                help="Host where AlgoEngine Exchange Simulator query API is listening.",
            )
            exchange_query_port = exchange_port_col.number_input(
                "Exchange query port",
                min_value=1,
                max_value=65535,
                value=int(st.session_state.get("dummy_exchange_query_port", 9602)),
                step=1,
                help="Port where Exchange Simulator returns captured FIX messages for validation.",
            )

        settings = {
            "gateway_type": gateway_type,
            "protocol": protocol,
            "host": host,
            "port": int(port),
            "client_port": int(client_port),
            "market_data_port": int(market_data_port),
            "admin_port": int(admin_port),
            "exchange_host": exchange_host,
            "exchange_query_port": int(exchange_query_port),
            "api_token": api_token,
            "verify_tls": bool(verify_tls),
            "timeout": float(timeout),
        }

        current_settings = st.session_state.get("trading_connection_settings")
        if current_settings != settings:
            st.session_state.trading_gateway_type = gateway_type
            st.session_state.trading_protocol = protocol
            st.session_state.trading_host = host
            st.session_state.trading_port = int(port)
            st.session_state.algoengine_client_port = int(client_port)
            st.session_state.algoengine_market_data_port = int(market_data_port)
            st.session_state.algoengine_admin_port = int(admin_port)
            st.session_state.dummy_exchange_host = exchange_host
            st.session_state.dummy_exchange_query_port = int(exchange_query_port)
            st.session_state.trading_api_token = api_token
            st.session_state.trading_verify_tls = bool(verify_tls)
            st.session_state.trading_timeout = float(timeout)
            st.session_state.trading_connection_settings = settings
            platform = rebuild_platform_for_connection(settings, platform)
            st.session_state.compliance_platform = platform

        if gateway_type == "demo":
            st.caption("Using the in-memory demo trading gateway.")
        elif gateway_type == "algoengine_tcp":
            st.caption(
                "Using AlgoEngine_TCP gateway: "
                f"client_orders={host}:{int(client_port)}, "
                f"market_data={host}:{int(market_data_port)}, "
                f"admin_commands={host}:{int(admin_port)}, "
                f"exchange_query={exchange_host}:{int(exchange_query_port)}"
            )
        else:
            st.caption(f"Using trading gateway: {protocol}://{host}:{int(port)}")

    return st.session_state.compliance_platform


def rebuild_platform_for_connection(settings: dict, existing_platform: CompliancePlatform) -> CompliancePlatform:
    if settings["gateway_type"] == "demo":
        gateway = DemoTradingSystemGateway()
    elif settings["gateway_type"] == "algoengine_tcp":
        gateway = AlgoEngineTcpGateway(
            AlgoEngineTcpConfig(
                host=settings["host"],
                client_port=settings["client_port"],
                market_data_port=settings["market_data_port"],
                admin_port=settings["admin_port"],
                exchange_host=settings["exchange_host"],
                exchange_query_port=settings["exchange_query_port"],
                timeout_seconds=settings["timeout"],
            )
        )
    else:
        gateway = HttpTradingSystemGateway(
            host=settings["host"],
            port=settings["port"],
            protocol=settings["protocol"],
            api_token=settings["api_token"] or None,
            verify_tls=settings["verify_tls"],
            request_timeout_seconds=settings["timeout"],
        )
    platform = CompliancePlatform(gateway)
    platform.knowledge_base = existing_platform.knowledge_base
    platform.trading_system = TradingSystemService(gateway)
    platform.agent_registry = ValidationAgentRegistry(platform.trading_system)
    platform.validator = TradingComplianceValidationService(platform.knowledge_base, platform.agent_registry)
    return platform


def render_agents_at_work() -> None:
    platform = get_demo_platform()
    knowledge = asyncio.run(platform.knowledge_base.current())
    registered_agents = set(platform.agent_registry.names())

    st.subheader("Agents at Work")
    st.write(
        "Review the agents available in the current TIA runtime and capture proposed new agents "
        "before implementing them in the backend."
    )

    st.markdown("### Validation agents")
    validation_rows = []
    for control in knowledge.controls:
        validation_rows.append(
            {
                "control_id": control.control_id,
                "control": control.name,
                "agent": control.validation_agent,
                "registered": "Yes" if control.validation_agent in registered_agents else "No",
                "scenario": control.scenario_name,
            }
        )
    st.dataframe(pd.DataFrame(validation_rows), hide_index=True, use_container_width=True)

    st.markdown("### Investigation agents")
    investigation_rows = [
        {
            "agent": "Planner Agent",
            "role": "Chooses the investigation path and decides whether to inspect market, order, or engine evidence first.",
        },
        {
            "agent": "Market Investigation Agent",
            "role": "Runs market data stress controls such as crossed, locked, and one-sided market checks.",
        },
        {
            "agent": "Order Investigation Agent",
            "role": "Runs pre-trade risk control checks such as parent-child, duplicate order, bad price, and market order behavior.",
        },
        {
            "agent": "Engine Investigation Agent",
            "role": "Runs engine behavior checks such as kill switch and maximum evaluation frequency.",
        },
        {
            "agent": "Regulatory Mapping Agent",
            "role": "Maps evidence and results back to the active TIA control catalog and citations.",
        },
        {
            "agent": "Critic Agent",
            "role": "Challenges the evidence, looks for contradictions, and lowers confidence where support is weak.",
        },
        {
            "agent": "Synthesizer Agent",
            "role": "Builds the final finding, confidence, conclusion, root cause, and recommended actions.",
        },
    ]
    st.dataframe(pd.DataFrame(investigation_rows), hide_index=True, use_container_width=True)

    st.markdown("### Add agent")
    with st.form("add_agent_form", clear_on_submit=True):
        agent_name = st.text_input("Name", placeholder="Example: Rapid Movement Retrace Agent")
        agent_description = st.text_area(
            "Short description of agent",
            placeholder="Describe what the agent should validate, what evidence it needs, and what pass/fail means.",
            height=110,
        )
        submitted = st.form_submit_button("Add agent", type="primary")

    if "proposed_agents" not in st.session_state:
        st.session_state.proposed_agents = []

    if submitted:
        clean_name = agent_name.strip()
        clean_description = agent_description.strip()
        if not clean_name or not clean_description:
            st.warning("Provide both agent name and short description before adding.")
        else:
            st.session_state.proposed_agents.append(
                {
                    "name": clean_name,
                    "description": clean_description,
                    "status": "Proposed in UI, backend implementation pending",
                }
            )
            st.success(f"Added proposed agent: {clean_name}")

    if st.session_state.proposed_agents:
        st.markdown("### Proposed agents")
        st.dataframe(pd.DataFrame(st.session_state.proposed_agents), hide_index=True, use_container_width=True)

    st.markdown("### Backend steps required")
    st.info(
        "Adding an agent here records the requirement for the demo session. To make it functional, "
        "the backend must still implement and register executable logic."
    )
    st.markdown(
        """
1. Create a new agent class in `app/agents/` that extends `ValidationAgent` and implements `evaluate()`.
2. Add or update the matching scenario behavior in the selected trading gateway, usually `app/trading/demo_gateway.py` and, if needed, `app/trading/algo_engine_gateway.py`.
3. Add a matching control entry in `app/knowledge/control_catalog.py` with `control_id`, `name`, `validation_agent`, `scenario_name`, expected behavior, parameters, and citations.
4. Register the new agent in `app/agents/registry.py` so the validation service can call it.
5. If the agent should participate in agentic investigations, route the new control from the relevant investigation agent under `app/investigation_agents/`.
6. Add or update tests under `tests/` to prove pass, fail, and review behavior.
7. Restart Streamlit or the API service so the new class and catalog entry are loaded.
        """
    )
def render_controls_table(controls) -> None:
    rows = []
    for control in controls:
        rows.append(
            {
                "control_id": control.control_id,
                "name": control.name,
                "agent": control.validation_agent,
                "scenario": control.scenario_name,
                "source_obligations": ", ".join(control.source_obligation_ids),
                "citations": "; ".join(control.citations),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
















