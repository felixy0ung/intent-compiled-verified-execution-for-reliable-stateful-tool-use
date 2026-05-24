from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOL_SANDBOX = ROOT / "third_party" / "ToolSandbox-main"
for path in (SRC, TOOL_SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pctu_pilot.llm_client import OpenAICompatibleClient  # noqa: E402
from pctu_pilot.rave_dsl import RaveRuntimeOptions  # noqa: E402
from pctu_pilot.toolsandbox_agents import RiskAdaptiveToolSandboxAgent  # noqa: E402
from tool_sandbox.common.execution_context import RoleType  # noqa: E402
from tool_sandbox.common.message_conversion import Message  # noqa: E402


class StubClient(OpenAICompatibleClient):
    def __init__(self) -> None:
        pass

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dynamic synthesis smoke test must not call the LLM")


def get_wifi_status() -> bool:
    return False


def set_wifi_status(on: bool) -> None:
    del on


def get_low_battery_mode_status() -> bool:
    return True


def set_low_battery_mode_status(on: bool) -> None:
    del on


def get_cellular_service_status() -> bool:
    return False


def set_cellular_service_status(on: bool) -> None:
    del on


def get_bluetooth_status() -> bool:
    return False


def set_bluetooth_status(on: bool) -> None:
    del on


def get_dark_mode_status() -> bool:
    return True


def set_dark_mode_status(on: bool) -> None:
    del on


def get_privacy_mode_status() -> bool:
    return False


def set_privacy_mode_status(on: bool) -> None:
    del on


def get_focus_mode_status() -> bool:
    return False


def set_focus_mode_status(enabled: bool) -> None:
    del enabled


def search_contacts(name: str = "") -> list[dict[str, str]]:
    del name
    return []


def available_tools() -> dict[str, Any]:
    return {
        "get_wifi_status": get_wifi_status,
        "set_wifi_status": set_wifi_status,
        "get_low_battery_mode_status": get_low_battery_mode_status,
        "set_low_battery_mode_status": set_low_battery_mode_status,
        "get_cellular_service_status": get_cellular_service_status,
        "set_cellular_service_status": set_cellular_service_status,
        "get_bluetooth_status": get_bluetooth_status,
        "set_bluetooth_status": set_bluetooth_status,
        "get_dark_mode_status": get_dark_mode_status,
        "set_dark_mode_status": set_dark_mode_status,
        "get_privacy_mode_status": get_privacy_mode_status,
        "set_privacy_mode_status": set_privacy_mode_status,
        "get_focus_mode_status": get_focus_mode_status,
        "set_focus_mode_status": set_focus_mode_status,
        "search_contacts": search_contacts,
    }


def make_agent() -> RiskAdaptiveToolSandboxAgent:
    return RiskAdaptiveToolSandboxAgent(
        client=StubClient(),
        method_name="dynamic synthesis smoke test",
        options=RaveRuntimeOptions(
            use_static_intent_machines=False,
            enable_dynamic_machine_synthesis=True,
        ),
    )


def one_user_message(content: str) -> list[Message]:
    return [Message(sender=RoleType.USER, recipient=RoleType.AGENT, content=content)]


def assert_equal(actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def test_dynamic_setting_machine_from_empty_registry() -> None:
    agent = make_agent()
    tools = available_tools()
    assert_equal(len(agent.rave_runtime.intent_machines), 0)

    first = agent._next_runtime_action(one_user_message("Turn on wifi"), tools)
    assert_equal(first, ("get_low_battery_mode_status", {}, "dynamic_read_low_battery_before_enable_wifi"))
    assert_equal("dynamic_setting_wifi" in agent.rave_runtime.intent_machine_by_type, True)
    assert_equal(agent.metrics.dynamic_synthesis_records, 1)
    assert_equal(agent.metrics.dynamic_synthesis_promotions, 1)

    agent.ledger.observe("get_low_battery_mode_status", {}, "True", None)
    second = agent._next_runtime_action(one_user_message("Turn on wifi"), tools)
    assert_equal(
        second,
        ("set_low_battery_mode_status", {"on": False}, "dynamic_disable_low_battery_before_enable_wifi"),
    )

    agent.ledger.observe("set_low_battery_mode_status", {"on": False}, "None", None)
    third = agent._next_runtime_action(one_user_message("Turn on wifi"), tools)
    assert_equal(third, ("set_wifi_status", {"on": True}, "dynamic_set_wifi_on"))


def test_dynamic_synthesis_rejects_unrelated_requests() -> None:
    agent = make_agent()
    tools = available_tools()
    action = agent._next_runtime_action(one_user_message("What is the stock symbol for Apple?"), tools)
    assert_equal(action, None)
    assert_equal(agent.metrics.dynamic_synthesis_records, 1)
    assert_equal(agent.metrics.dynamic_synthesis_promotions, 0)
    assert_equal(agent.metrics.dynamic_synthesis_rejections, 1)


def test_synthesized_compiler_counterexamples_do_not_match() -> None:
    agent = make_agent()
    tools = available_tools()
    action = agent._next_runtime_action(one_user_message("Turn off cellular"), tools)
    assert_equal(action, ("set_cellular_service_status", {"on": False}, "dynamic_set_cellular_off"))
    machine = agent.rave_runtime.intent_machine_by_type["dynamic_setting_cellular"]
    for text in (
        "What is the weather at the Grand Canyon?",
        "Find my boss's phone number.",
        "Send a message to Alice saying hello.",
    ):
        assert_equal(machine.compiler(text, text, tools), None)


def test_dynamic_affordance_template_induces_unseen_setting_machines() -> None:
    agent = make_agent()
    tools = available_tools()

    first = agent._next_runtime_action(one_user_message("Turn on bluetooth"), tools)
    assert_equal(first, ("set_bluetooth_status", {"on": True}, "dynamic_set_bluetooth_on"))
    assert_equal("dynamic_setting_bluetooth" in agent.rave_runtime.intent_machine_by_type, True)
    audit = agent.dynamic_synthesizer.audit[-1]
    assert_equal(audit.decision, "promoted")
    assert_equal("affordance_template_induced:bluetooth" in audit.details, True)

    agent.ledger.observe("set_bluetooth_status", {"on": True}, "None", None)
    status = agent._next_runtime_action(one_user_message("Check bluetooth status"), tools)
    assert_equal(status, None)

    second = agent._next_runtime_action(one_user_message("Disable dark mode"), tools)
    assert_equal(second, ("set_dark_mode_status", {"on": False}, "dynamic_set_dark_mode_off"))
    assert_equal("dynamic_setting_dark_mode" in agent.rave_runtime.intent_machine_by_type, True)


def test_dynamic_affordance_template_rejects_bad_setter_signature() -> None:
    agent = make_agent()
    tools = available_tools()
    action = agent._next_runtime_action(one_user_message("Enable focus mode"), tools)
    assert_equal(action, None)
    audit = agent.dynamic_synthesizer.audit[-1]
    assert_equal(audit.decision, "rejected")
    assert_equal(audit.details, ("set_focus_mode_status_missing_on_parameter",))


def main() -> None:
    test_dynamic_setting_machine_from_empty_registry()
    test_dynamic_synthesis_rejects_unrelated_requests()
    test_synthesized_compiler_counterexamples_do_not_match()
    test_dynamic_affordance_template_induces_unseen_setting_machines()
    test_dynamic_affordance_template_rejects_bad_setter_signature()
    print("dynamic machine synthesis smoke tests passed")


if __name__ == "__main__":
    main()
