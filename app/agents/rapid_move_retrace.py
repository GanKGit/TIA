from app.agents.base import ValidationAgent


class RapidMoveRetraceAgent(ValidationAgent):
    agent_name = "rapid-move-retrace-agent"

    def evaluate(self, control, snapshot, observation):
        passed = bool(observation.metrics.get("risk_limits_respected")) and int(observation.metrics.get("uncontrolled_orders", 1)) == 0
        return self.result(control, observation, passed, str(observation.metrics), "RAPID_MOVE_LIMITS_RESPECTED", "RAPID_MOVE_CONTROL_FAILURE", "Apply risk limits through rapid movement and retracement without uncontrolled orders.")

