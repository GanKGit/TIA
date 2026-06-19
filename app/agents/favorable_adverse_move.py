from app.agents.base import ValidationAgent


class FavorableAdverseMoveAgent(ValidationAgent):
    agent_name = "favorable-adverse-move-agent"

    def evaluate(self, control, snapshot, observation):
        passed = bool(observation.metrics.get("limits_applied_both_directions"))
        return self.result(control, observation, passed, str(observation.metrics), "BIDIRECTIONAL_LIMITS_APPLIED", "ASYMMETRIC_RISK_CONTROL", "Apply equivalent risk controls when the market moves both in and out of favor.")

