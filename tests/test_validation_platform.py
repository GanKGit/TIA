from __future__ import annotations

import unittest
from collections import Counter
from unittest.mock import patch

from app.knowledge.control_catalog import initial_mvp_controls
from app.agents.market_order_check import MarketOrderCheckAgent
from app.agents.duplicate_order import DuplicateOrderAgent
from app.agents.parent_child import ParentChildAgent
from app.agents.bad_price_breach import BadPriceBreachAgent
from app.agents.kill_switch import KillSwitchAgent
from app.agents.max_evaluation_frequency import MaxEvaluationFrequencyAgent
from app.agents.crossed_market import CrossedMarketAgent
from app.agents.locked_market import LockedMarketAgent
from app.agents.one_sided_market import OneSidedMarketAgent
from app.models.knowledge import KnowledgeBaseVersion
from app.models.validation import ComplianceControl, ScenarioObservation
from app.services.compliance_pipeline import CompliancePlatform
from app.models.investigation import InvestigationRequest
from app.services.investigation_service import AgenticInvestigationService
from app.trading.demo_gateway import DemoTradingSystemGateway
from app.trading.factory import gateway_from_environment
from app.trading.algo_engine_gateway import AlgoEngineTcpGateway
from app.trading.http_gateway import HttpTradingSystemGateway
from app.models.validation import ScenarioRequest
from datetime import datetime, timezone


class ValidationPlatformTests(unittest.IsolatedAsyncioTestCase):
    async def test_agentic_market_stress_case_runs_full_investigation_path(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        finding = await AgenticInvestigationService(platform).investigate(
            InvestigationRequest(preset="market_stress_incident")
        )

        self.assertEqual("pass", finding.final_status.value)
        self.assertEqual(9, len(finding.validation_results))
        self.assertEqual("planner-agent", finding.agent_trace[0].agent_name)
        self.assertEqual("market-investigation-agent", finding.agent_trace[1].agent_name)
        self.assertIn("STRESS-001", finding.agent_trace[1].selected_controls)

    async def test_agentic_pre_trade_risk_case_uses_order_first_path(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        finding = await AgenticInvestigationService(platform).investigate(
            InvestigationRequest(preset="pre_trade_risk_control_investigation")
        )

        self.assertEqual("pass", finding.final_status.value)
        self.assertEqual(6, len(finding.validation_results))
        self.assertEqual("order-investigation-agent", finding.agent_trace[1].agent_name)
        self.assertNotIn("STRESS-001", {result.control_id for result in finding.validation_results})
    async def test_market_data_stress_case_can_detect_disabled_protections(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        finding = await AgenticInvestigationService(platform).investigate(
            InvestigationRequest(preset="market_stress_incident", parameters={"market_protections_enabled": False})
        )

        failed = {result.control_id for result in finding.validation_results if result.status.value == "fail"}
        self.assertEqual("fail", finding.final_status.value)
        self.assertTrue({"STRESS-001", "STRESS-002", "STRESS-003"}.issubset(failed))

    async def test_pre_trade_risk_case_can_detect_control_failures(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        finding = await AgenticInvestigationService(platform).investigate(
            InvestigationRequest(preset="pre_trade_risk_control_investigation", parameters={"duplicate_rejected": False, "bad_price_blocked": False})
        )

        failed = {result.control_id for result in finding.validation_results if result.status.value == "fail"}
        self.assertEqual("fail", finding.final_status.value)
        self.assertTrue({"CTRL-002", "CTRL-003"}.issubset(failed))


    async def test_investigative_experience_can_flip_market_case_to_fail(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        finding = await AgenticInvestigationService(platform).investigate(
            InvestigationRequest(
                preset="market_stress_incident",
                parameters={"symbol": "AAPL", "market_protections_enabled": False},
            )
        )

        failed = {result.control_id for result in finding.validation_results if result.status.value == "fail"}
        self.assertEqual("fail", finding.final_status.value)
        self.assertTrue({"STRESS-001", "STRESS-002", "STRESS-003"}.issubset(failed))

    async def test_investigative_experience_can_flip_order_case_to_pass(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        finding = await AgenticInvestigationService(platform).investigate(
            InvestigationRequest(
                preset="pre_trade_risk_control_investigation",
                parameters={
                    "symbol": "AAPL",
                    "duplicate_rejected": True,
                    "bad_price_blocked": True,
                    "duplicate_client_order_id": "DUP-AAPL-001",
                    "bad_price": 210.0,
                    "order_quantity": 100,
                },
            )
        )

        self.assertEqual("pass", finding.final_status.value)
        self.assertFalse(finding.failed_controls)
    async def test_investigation_parameters_are_preserved(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        parameters = {"symbol": "MSFT", "bad_price": 250.25, "duplicate_client_order_id": "DUP-MSFT-001"}
        finding = await AgenticInvestigationService(platform).investigate(
            InvestigationRequest(
                preset="pre_trade_risk_control_investigation",
                question="Investigate user-selected MSFT order-control parameters.",
                parameters=parameters,
            )
        )

        self.assertEqual(parameters, finding.regulatory_mapping["request_parameters"])
        self.assertIn("Parameters:", finding.agent_trace[0].observations[1])
    async def test_initial_version_runs_nine_unique_agents(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        knowledge = await platform.knowledge_base.current()
        run = await platform.validator.validate_system("TRADING-DEMO-01")

        self.assertEqual(9, len(platform.agent_registry.names()))
        self.assertEqual(9, len(knowledge.controls))
        self.assertEqual(9, len(run.results))
        self.assertEqual(9, len({result.agent_name for result in run.results}))
        self.assertEqual({"pass": 9}, dict(Counter(item.status.value for item in run.results)))

    async def test_agent_detects_kill_switch_failure(self) -> None:
        gateway = DemoTradingSystemGateway({"kill_switch": {"new_orders_rejected": False}})
        platform = CompliancePlatform(gateway)
        await platform.initialize()
        run = await platform.validator.validate_system("TRADING-DEMO-FAIL")
        result = next(item for item in run.results if item.control_id == "CTRL-004")

        self.assertEqual("fail", result.status.value)
        self.assertIn("KILL_SWITCH_FAILED", result.reason_codes)

    async def test_market_order_check_control_runs_against_demo_evidence(self) -> None:
        platform = CompliancePlatform()
        await platform.initialize()
        run = await platform.validator.validate_system("TRADING-DEMO-01")
        result = next(item for item in run.results if item.control_id == "CTRL-006")

        self.assertEqual("Market order check", result.control_name)
        self.assertEqual("market-order-check-agent", result.agent_name)
        self.assertEqual("pass", result.status.value)
        self.assertIn("MARKET_ORDER_CONVERTED_TO_LIMIT", result.reason_codes)


    async def test_http_gateway_uses_configured_port_and_endpoints(self) -> None:
        calls = []

        class RecordingGateway(HttpTradingSystemGateway):
            async def _request_json(self, method, path, payload=None, allow_empty=False):
                calls.append((method, path, payload, allow_empty))
                if method == "GET":
                    return {"configuration": {}, "capabilities": [], "health": {}}
                return {} if allow_empty else {"accepted": True, "metrics": {"trading_halted": True}}

        gateway = RecordingGateway("trade-host", 18080, api_token="secret")
        snapshot = await gateway.get_snapshot("SYS 1")
        request = ScenarioRequest(scenario_name="kill_switch", correlation_id="corr 1")
        await gateway.execute_scenario("SYS 1", request)
        await gateway.reset_scenario("SYS 1", "corr 1")
        await gateway.close()

        self.assertEqual("SYS 1", snapshot.system_id)
        self.assertEqual("http://trade-host:18080", gateway.base_url)
        self.assertEqual(
            [
                "/systems/SYS%201/snapshot",
                "/systems/SYS%201/scenarios",
                "/systems/SYS%201/scenarios/corr%201/reset",
            ],
            [call[1] for call in calls],
        )

    def test_environment_factory_builds_http_port_gateway(self) -> None:
        environment = {
            "TRADING_SYSTEM_GATEWAY": "http",
            "TRADING_SYSTEM_HOST": "localhost",
            "TRADING_SYSTEM_PORT": "19090",
        }
        with patch.dict("os.environ", environment, clear=False):
            gateway = gateway_from_environment()
        self.assertIsInstance(gateway, HttpTradingSystemGateway)
        self.assertEqual("http://localhost:19090", gateway.base_url)

    def test_environment_factory_builds_algoengine_tcp_gateway(self) -> None:
        environment = {
            "TRADING_SYSTEM_GATEWAY": "algoengine_tcp",
            "ALGOENGINE_HOST": "127.0.0.1",
            "ALGOENGINE_CLIENT_PORT": "9500",
            "ALGOENGINE_MARKET_DATA_PORT": "9501",
            "ALGOENGINE_ADMIN_PORT": "9502",
            "DUMMY_EXCHANGE_HOST": "10.0.0.5",
            "DUMMY_EXCHANGE_QUERY_PORT": "19982",
        }
        with patch.dict("os.environ", environment, clear=False):
            gateway = gateway_from_environment()

        self.assertIsInstance(gateway, AlgoEngineTcpGateway)
        self.assertEqual("127.0.0.1", gateway.config.host)
        self.assertEqual(9500, gateway.config.client_port)
        self.assertEqual(9501, gateway.config.market_data_port)
        self.assertEqual("10.0.0.5", gateway.config.exchange_host)
        self.assertEqual(19982, gateway.config.exchange_query_port)


    def test_market_order_check_agent_passes_when_market_order_is_converted_to_limit(self) -> None:
        control = ComplianceControl(
            control_id="C001",
            name="Market Order Check",
            description="The engine should convert market orders into limit orders before exchange submission.",
            expected_behavior="Client market orders are converted into limit orders and tag 40=1 is never sent to exchange.",
            validation_agent="market-order-check-agent",
            scenario_name="market_order_check",
        )
        observation = ScenarioObservation(
            scenario_name="market_order_check",
            correlation_id="test-c001-pass",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            metrics={
                "client_order": {"55": "AAPL", "54": "1", "38": "100", "40": "1"},
                "exchange_orders": [
                    {"55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
                ],
            },
        )

        result = MarketOrderCheckAgent(None).evaluate(control, None, observation)

        self.assertEqual("pass", result.status.value)
        self.assertIn("MARKET_ORDER_CONVERTED_TO_LIMIT", result.reason_codes)

    def test_market_order_check_agent_fails_when_market_order_reaches_exchange(self) -> None:
        control = ComplianceControl(
            control_id="C001",
            name="Market Order Check",
            description="The engine should slice aggressive limit orders when client sends a market order.",
            expected_behavior="Client market orders are converted into limit orders and tag 40=1 is never sent to exchange.",
            validation_agent="market-order-check-agent",
            scenario_name="market_order_check",
        )
        observation = ScenarioObservation(
            scenario_name="market_order_check",
            correlation_id="test-c001-fail",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            metrics={
                "client_order": {"55": "AAPL", "54": "1", "38": "100", "40": "1"},
                "exchange_orders": [
                    {"55": "AAPL", "54": "1", "38": "250", "40": "1"},
                ],
            },
        )

        result = MarketOrderCheckAgent(None).evaluate(control, None, observation)

        self.assertEqual("fail", result.status.value)
        self.assertIn("MARKET_ORDER_SENT_OR_UNSLICED", result.reason_codes)

    def test_duplicate_order_agent_passes_when_client_reject_is_returned(self) -> None:
        control = ComplianceControl(
            control_id="C002",
            name="Duplicate orders",
            description="Duplicate submissions are rejected on the client channel.",
            expected_behavior="Duplicate submissions are rejected and only one order is accepted.",
            validation_agent="duplicate-order-agent",
            scenario_name="duplicate_order",
        )
        observation = ScenarioObservation(
            scenario_name="duplicate_order",
            correlation_id="test-c002-pass",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            metrics={
                "first_client_response": {"11": "C002-DUP-AAPL-001", "39": "0", "150": "0", "58": "Accepted."},
                "second_client_response": {"11": "C002-DUP-AAPL-001", "39": "8", "150": "8", "58": "Duplicate Order ID"},
                "orders_accepted": 1,
                "duplicate_rejected": True,
                "client_reject_sent": True,
            },
        )

        result = DuplicateOrderAgent(None).evaluate(control, None, observation)

        self.assertEqual("pass", result.status.value)
        self.assertIn("DUPLICATE_REJECTED", result.reason_codes)

    def test_duplicate_order_agent_fails_when_duplicate_is_accepted(self) -> None:
        control = ComplianceControl(
            control_id="C002",
            name="Duplicate orders",
            description="Duplicate submissions are rejected on the client channel.",
            expected_behavior="Duplicate submissions are rejected and only one order is accepted.",
            validation_agent="duplicate-order-agent",
            scenario_name="duplicate_order",
        )
        observation = ScenarioObservation(
            scenario_name="duplicate_order",
            correlation_id="test-c002-fail",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            metrics={
                "first_client_response": {"11": "C002-DUP-AAPL-001", "39": "0", "150": "0"},
                "second_client_response": {"11": "C002-DUP-AAPL-001", "39": "0", "150": "0"},
                "orders_accepted": 2,
                "duplicate_rejected": False,
            },
        )

        result = DuplicateOrderAgent(None).evaluate(control, None, observation)

        self.assertEqual("fail", result.status.value)
        self.assertIn("DUPLICATE_ACCEPTED", result.reason_codes)

    def test_seeded_parent_child_agent_evaluates_link_and_invalid_child_rejection(self) -> None:
        control = ComplianceControl(control_id="CTRL-001", name="Parent-child orders", description="", expected_behavior="Child orders remain linked.", validation_agent="parent-child-agent", scenario_name="parent_child")
        observation = ScenarioObservation(scenario_name="parent_child", correlation_id="pc-pass", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"parent_response": {"39": "0", "150": "0"}, "child_response": {"39": "0", "150": "0"}, "invalid_child_response": {"39": "8", "150": "8"}, "parent_order_id": "P1", "child_parent_id": "P1"})
        result = ParentChildAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)
        self.assertIn("PARENT_CHILD_ENFORCED", result.reason_codes)

    def test_seeded_parent_child_agent_fails_missing_parent_link(self) -> None:
        control = ComplianceControl(control_id="CTRL-001", name="Parent-child orders", description="", expected_behavior="Child orders remain linked.", validation_agent="parent-child-agent", scenario_name="parent_child")
        observation = ScenarioObservation(scenario_name="parent_child", correlation_id="pc-fail", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"parent_response": {"39": "0", "150": "0"}, "child_response": {"39": "0", "150": "0"}, "invalid_child_response": {"39": "8", "150": "8"}, "parent_order_id": "P1", "child_parent_id": "WRONG"})
        result = ParentChildAgent(None).evaluate(control, None, observation)
        self.assertEqual("fail", result.status.value)

    def test_seeded_bad_price_agent_requires_reject_halt_and_no_exchange_leak(self) -> None:
        control = ComplianceControl(control_id="CTRL-003", name="Bad-price breach", description="", expected_behavior="Bad price halts.", validation_agent="bad-price-breach-agent", scenario_name="bad_price_breach")
        observation = ScenarioObservation(scenario_name="bad_price_breach", correlation_id="bp-pass", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"bad_order": {"11": "BAD1"}, "bad_order_response": {"39": "8", "150": "8", "58": "BAD_PRICE_BREACH"}, "exchange_orders": [], "breach_detected": True, "trading_halted": True})
        result = BadPriceBreachAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)
        self.assertIn("BAD_PRICE_HALTED", result.reason_codes)

    def test_seeded_bad_price_agent_fails_if_bad_order_reaches_exchange(self) -> None:
        control = ComplianceControl(control_id="CTRL-003", name="Bad-price breach", description="", expected_behavior="Bad price halts.", validation_agent="bad-price-breach-agent", scenario_name="bad_price_breach")
        observation = ScenarioObservation(scenario_name="bad_price_breach", correlation_id="bp-fail", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"bad_order": {"11": "BAD1"}, "bad_order_response": {"39": "8", "150": "8"}, "exchange_orders": [{"11": "BAD1"}], "breach_detected": True, "trading_halted": True})
        result = BadPriceBreachAgent(None).evaluate(control, None, observation)
        self.assertEqual("fail", result.status.value)

    def test_seeded_kill_switch_agent_requires_halt_and_post_halt_reject(self) -> None:
        control = ComplianceControl(control_id="CTRL-004", name="Kill switch", description="", expected_behavior="Kill halts.", validation_agent="kill-switch-agent", scenario_name="kill_switch")
        observation = ScenarioObservation(scenario_name="kill_switch", correlation_id="ks-pass", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"trading_halted": True, "post_halt_order_response": {"39": "8", "150": "8"}, "cancel_signal_sent": True})
        result = KillSwitchAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)
        self.assertIn("KILL_SWITCH_EFFECTIVE", result.reason_codes)

    def test_seeded_max_eval_agent_checks_effective_rate_limit(self) -> None:
        control = ComplianceControl(control_id="CTRL-005", name="Maximum evaluation frequency", description="", expected_behavior="Rate limited.", validation_agent="max-evaluation-frequency-agent", scenario_name="max_evaluation_frequency", parameters={"max_hz": 10})
        observation = ScenarioObservation(scenario_name="max_evaluation_frequency", correlation_id="mef-pass", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"evaluation_timestamps_ms": [0, 100, 200, 300], "configured_max_hz": 10, "rate_limited": True})
        result = MaxEvaluationFrequencyAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)

    def test_seeded_max_eval_agent_fails_excessive_effective_rate(self) -> None:
        control = ComplianceControl(control_id="CTRL-005", name="Maximum evaluation frequency", description="", expected_behavior="Rate limited.", validation_agent="max-evaluation-frequency-agent", scenario_name="max_evaluation_frequency", parameters={"max_hz": 10})
        observation = ScenarioObservation(scenario_name="max_evaluation_frequency", correlation_id="mef-fail", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"evaluation_timestamps_ms": [0, 10, 20], "configured_max_hz": 10, "rate_limited": False})
        result = MaxEvaluationFrequencyAgent(None).evaluate(control, None, observation)
        self.assertEqual("fail", result.status.value)

    def test_seeded_max_eval_agent_passes_when_observed_rate_equals_limit_without_throttle(self) -> None:
        control = ComplianceControl(control_id="CTRL-005", name="Maximum evaluation frequency", description="", expected_behavior="Rate limited.", validation_agent="max-evaluation-frequency-agent", scenario_name="max_evaluation_frequency", parameters={"max_hz": 10})
        observation = ScenarioObservation(scenario_name="max_evaluation_frequency", correlation_id="mef-at-limit", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"observed_hz": 10, "configured_max_hz": 10, "rate_limited": False})
        result = MaxEvaluationFrequencyAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)
        self.assertIn("EVALUATION_RATE_WITHIN_LIMIT", result.reason_codes)
    def test_seeded_crossed_market_agent_requires_detection_and_uncrossing(self) -> None:
        control = ComplianceControl(control_id="STRESS-001", name="Crossed market", description="", expected_behavior="Restrict crossed market.", validation_agent="crossed-market-agent", scenario_name="crossed_market")
        observation = ScenarioObservation(scenario_name="crossed_market", correlation_id="cm-pass", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"crossed_market_detected": True, "market_data_uncrossed": True})
        result = CrossedMarketAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)

    def test_seeded_locked_market_agent_requires_detection_and_hold_or_cancel(self) -> None:
        control = ComplianceControl(control_id="STRESS-002", name="Locked market", description="", expected_behavior="Restrict locked market.", validation_agent="locked-market-agent", scenario_name="locked_market")
        observation = ScenarioObservation(scenario_name="locked_market", correlation_id="lm-pass", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"locked_market_detected": True, "orders_cancelled_or_held": True})
        result = LockedMarketAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)

    def test_seeded_one_sided_market_agent_requires_hold_and_no_exchange_leak(self) -> None:
        control = ComplianceControl(control_id="STRESS-003", name="One-sided market", description="", expected_behavior="Restrict one-sided market.", validation_agent="one-sided-market-agent", scenario_name="one_sided_market")
        observation = ScenarioObservation(scenario_name="one_sided_market", correlation_id="osm-pass", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), metrics={"one_sided_market_detected": True, "order_held": True, "exchange_orders": []})
        result = OneSidedMarketAgent(None).evaluate(control, None, observation)
        self.assertEqual("pass", result.status.value)


if __name__ == "__main__":
    unittest.main()





