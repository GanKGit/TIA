from __future__ import annotations

from datetime import datetime, timezone

from app.investigation_agents.base import InvestigationState
from app.models.investigation import InvestigationFinding, InvestigationStep
from app.models.validation import ValidationResult, ValidationStatus


class DecisionSynthesizerAgent:
    agent_name = "decision-synthesizer-agent"

    async def run(self, state: InvestigationState) -> InvestigationFinding:
        results = state.ordered_results
        failed = [item for item in results if item.status == ValidationStatus.FAIL]
        review = [item for item in results if item.status == ValidationStatus.REVIEW]
        if failed:
            final_status = ValidationStatus.FAIL
            conclusion = "Compliance risk detected in the investigated path."
            root_cause = "One or more deterministic validation controls failed during the selected investigation path."
        elif review or state.contradictions:
            final_status = ValidationStatus.REVIEW
            conclusion = "Investigation requires human review before a compliance decision is finalized."
            root_cause = "Evidence is incomplete, contradictory, or dependent on unavailable specialist coverage."
        else:
            final_status = ValidationStatus.PASS
            conclusion = "No compliance breach found for the simulated investigation path."
            root_cause = "Market, order, and engine-control evidence matched expected protective behavior."

        confidence, confidence_factors = _score_confidence(results, len(state.steps), len(state.contradictions))
        if final_status == ValidationStatus.FAIL:
            confidence = min(confidence, 0.88)
        if final_status == ValidationStatus.REVIEW:
            confidence = min(confidence, 0.76)
        if state.contradictions:
            final_status = ValidationStatus.REVIEW
            confidence = min(confidence, 0.72)

        evidence_summary = [
            f"{item.control_id} {item.control_name}: {item.status.value.upper()} - {', '.join(item.reason_codes)}"
            for item in results
        ]
        recommended_actions = []
        if failed:
            recommended_actions.extend(remediation for item in failed for remediation in item.remediation)
        if review:
            recommended_actions.append("Collect missing evidence or deploy the missing specialist validation agent before production sign-off.")
        if state.contradictions:
            recommended_actions.append("Resolve evidence contradictions before treating this investigation as final.")
        if not recommended_actions:
            recommended_actions.append("Retain investigation trace and validation evidence for audit replay.")

        state.add_step(
            InvestigationStep(
                agent_name=self.agent_name,
                action="Synthesize agent trace, validation evidence, regulatory mapping, and critic findings.",
                decision=conclusion,
                selected_controls=[item.control_id for item in results],
                observations=evidence_summary + confidence_factors,
                next_step="completed",
            )
        )
        return InvestigationFinding(
            system_id=state.request.system_id,
            question=state.request.question,
            preset=state.request.preset,
            started_at=state.started_at,
            completed_at=datetime.now(timezone.utc),
            final_status=final_status,
            conclusion=conclusion,
            confidence=confidence,
            human_review_required=bool(review or state.contradictions),
            root_cause=root_cause,
            evidence_summary=evidence_summary,
            recommended_actions=recommended_actions,
            agent_trace=state.steps,
            validation_results=results,
            regulatory_mapping={**state.regulatory_mapping, "confidence_factors": confidence_factors, "request_parameters": state.request.parameters},
            contradictions=state.contradictions,
        )

def _score_confidence(results: list[ValidationResult], trace_steps: int, contradiction_count: int) -> tuple[float, list[str]]:
    total = len(results)
    if total == 0:
        return 0.35, ["confidence: no validation results were available"]

    pass_count = sum(1 for item in results if item.status == ValidationStatus.PASS)
    fail_count = sum(1 for item in results if item.status == ValidationStatus.FAIL)
    review_count = sum(1 for item in results if item.status == ValidationStatus.REVIEW)
    evidence_count = sum(1 for item in results if item.evidence)
    citation_count = sum(1 for item in results if item.citations)
    control_coverage = min(total / 9.0, 1.0)
    pass_ratio = pass_count / total
    evidence_ratio = evidence_count / total
    citation_ratio = citation_count / total
    path_bonus = min(trace_steps, 7) * 0.005

    score = 0.50
    score += 0.18 * control_coverage
    score += 0.17 * pass_ratio
    score += 0.08 * evidence_ratio
    score += 0.04 * citation_ratio
    score += path_bonus
    score -= 0.08 * fail_count
    score -= 0.06 * review_count
    score -= 0.10 * contradiction_count
    score = max(0.30, min(score, 0.97))

    factors = [
        f"confidence: control coverage {total}/9 contributes {0.18 * control_coverage:.2f}",
        f"confidence: pass ratio {pass_count}/{total} contributes {0.17 * pass_ratio:.2f}",
        f"confidence: evidence coverage {evidence_count}/{total} contributes {0.08 * evidence_ratio:.2f}",
        f"confidence: citation coverage {citation_count}/{total} contributes {0.04 * citation_ratio:.2f}",
        f"confidence: trace depth {trace_steps} contributes {path_bonus:.2f}",
    ]
    if fail_count:
        factors.append(f"confidence: failed controls penalty {fail_count} x 0.08")
    if review_count:
        factors.append(f"confidence: review controls penalty {review_count} x 0.06")
    if contradiction_count:
        factors.append(f"confidence: contradiction penalty {contradiction_count} x 0.10")
    factors.append(f"confidence: final score {score:.2f}")
    return round(score, 2), factors


