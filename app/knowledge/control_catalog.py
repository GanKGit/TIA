from __future__ import annotations

from app.models.validation import ComplianceControl


def initial_mvp_controls() -> list[ComplianceControl]:
    """Nine active controls for the base trading-system validation MVP."""
    return [
        _control("CTRL-001", "Parent-child orders", "parent-child-agent", "parent_child", "Child orders remain linked to and constrained by the parent order."),
        _control("CTRL-002", "Duplicate orders", "duplicate-order-agent", "duplicate_order", "Duplicate submissions are rejected and only one order is accepted."),
        _control("CTRL-003", "Bad-price breach", "bad-price-breach-agent", "bad_price_breach", "The engine detects a bad-price breach and halts trading."),
        _control("CTRL-004", "Kill switch", "kill-switch-agent", "kill_switch", "A kill signal halts trading and rejects all new orders."),
        _control("CTRL-005", "Maximum evaluation frequency", "max-evaluation-frequency-agent", "max_evaluation_frequency", "Evaluation frequency does not exceed the approved maximum.", {"max_hz": 10}),
        _control("CTRL-006", "Market order check", "market-order-check-agent", "market_order_check", "Client market orders are converted to limit orders before exchange submission."),
        _control("STRESS-001", "Crossed market", "crossed-market-agent", "crossed_market", "The engine detects a crossed market and applies the approved restriction."),
        _control("STRESS-002", "Locked market", "locked-market-agent", "locked_market", "The engine detects a locked market and applies the approved restriction."),
        _control("STRESS-003", "One-sided market", "one-sided-market-agent", "one_sided_market", "The engine restricts trading when a two-sided market is unavailable."),
    ]



def _control(
    control_id: str,
    name: str,
    agent: str,
    scenario: str,
    expected: str,
    parameters: dict | None = None,
) -> ComplianceControl:
    return ComplianceControl(
        control_id=control_id,
        name=name,
        description=expected,
        expected_behavior=expected,
        validation_agent=agent,
        scenario_name=scenario,
        parameters=parameters or {},
        citations=["TIA MVP control catalog"],
    )
