from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Callable

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
        raise AssertionError("dynamic affordance generalization should not call the LLM")


def make_getter(state: dict[str, bool], name: str) -> Callable[[], bool]:
    def getter() -> bool:
        return state[name]

    return getter


def make_setter(state: dict[str, bool], name: str) -> Callable[[bool], None]:
    def setter(on: bool) -> None:
        state[name] = bool(on)

    return setter


def set_focus_mode_status(enabled: bool) -> None:
    del enabled


def build_tools(state: dict[str, bool]) -> dict[str, Callable[..., Any]]:
    tools: dict[str, Callable[..., Any]] = {}
    for name in state:
        tools[f"get_{name}_status"] = make_getter(state, name)
        tools[f"set_{name}_status"] = make_setter(state, name)
    tools["get_focus_mode_status"] = lambda: False
    tools["set_focus_mode_status"] = set_focus_mode_status
    tools["search_stock"] = lambda query="": {"symbol": "AAPL", "query": query}
    return tools


def make_agent() -> RiskAdaptiveToolSandboxAgent:
    return RiskAdaptiveToolSandboxAgent(
        client=StubClient(),
        method_name="dynamic affordance generalization",
        options=RaveRuntimeOptions(
            use_static_intent_machines=False,
            enable_dynamic_machine_synthesis=True,
        ),
    )


def one_user_message(content: str) -> list[Message]:
    return [Message(sender=RoleType.USER, recipient=RoleType.AGENT, content=content)]


def expected_setting(request: str) -> str:
    lowered = request.lower()
    for setting in ("bluetooth", "dark_mode", "privacy_mode", "roaming_data", "auto_sync"):
        if setting.replace("_", " ") in lowered or setting in lowered or setting.replace("_", "") in lowered:
            return setting
    if "focus mode" in lowered:
        return "focus_mode"
    return ""


def expected_on(request: str) -> bool | None:
    lowered = request.lower()
    if any(phrase in lowered for phrase in ("turn off", "disable", "shut off", "switch off")):
        return False
    if any(phrase in lowered for phrase in ("turn on", "enable", "switch on")):
        return True
    return None


def run_case(agent: RiskAdaptiveToolSandboxAgent, tools: dict[str, Callable[..., Any]], request: str) -> dict[str, Any]:
    before_machines = set(agent.rave_runtime.intent_machine_by_type)
    before_audits = len(agent.dynamic_synthesizer.audit)
    action = agent._next_runtime_action(one_user_message(request), tools)
    new_audits = agent.dynamic_synthesizer.audit[before_audits:]

    row: dict[str, Any] = {
        "request": request,
        "action_tool": "" if action is None else action[0],
        "action_args": "" if action is None else json.dumps(action[1], sort_keys=True),
        "action_reason": "" if action is None else action[2],
        "new_machine": "",
        "audit_decision": "" if not new_audits else new_audits[-1].decision,
        "audit_details": "" if not new_audits else ";".join(new_audits[-1].details),
        "success": 0,
        "expected_rejection": 0,
    }

    after_machines = set(agent.rave_runtime.intent_machine_by_type)
    promoted = sorted(after_machines - before_machines)
    if promoted:
        row["new_machine"] = promoted[0]

    target = expected_setting(request)
    desired = expected_on(request)
    if target == "focus_mode":
        row["expected_rejection"] = 1
        row["success"] = int(action is None and row["audit_decision"] == "rejected")
        return row
    if target and desired is not None:
        expected_tool = f"set_{target}_status"
        row["success"] = int(
            action is not None
            and action[0] == expected_tool
            and action[1] == {"on": desired}
            and row["audit_decision"] in {"promoted", "already_registered", ""}
        )
        if action is not None:
            tools[action[0]](**action[1])
            agent.ledger.observe(action[0], action[1], "None", None)
        return row

    row["expected_rejection"] = 1
    row["success"] = int(action is None)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate ICVE's dynamic affordance-template induction on held-out "
            "regular boolean-setting APIs that are absent from the static registry."
        )
    )
    parser.add_argument("--output-dir", default="results/dynamic_affordance_generalization")
    args = parser.parse_args()

    state = {
        "bluetooth": False,
        "dark_mode": True,
        "privacy_mode": False,
        "roaming_data": False,
        "auto_sync": True,
    }
    tools = build_tools(state)
    agent = make_agent()
    requests = [
        "Turn on bluetooth",
        "Disable dark mode",
        "Enable privacy mode",
        "Turn on roaming data",
        "Switch off auto sync",
        "Enable focus mode",
        "What is the stock symbol for Apple?",
    ]
    rows = [run_case(agent, tools, request) for request in requests]

    promoted = [
        audit
        for audit in agent.dynamic_synthesizer.audit
        if audit.decision == "promoted" and audit.candidate_intent_type
    ]
    rejected = [audit for audit in agent.dynamic_synthesizer.audit if audit.decision == "rejected"]
    summary = {
        "cases": len(rows),
        "successes": sum(int(row["success"]) for row in rows),
        "success_rate": sum(int(row["success"]) for row in rows) / len(rows),
        "positive_cases": sum(1 for row in rows if not int(row["expected_rejection"])),
        "positive_successes": sum(
            int(row["success"]) for row in rows if not int(row["expected_rejection"])
        ),
        "rejection_cases": sum(int(row["expected_rejection"]) for row in rows),
        "rejection_successes": sum(
            int(row["success"]) for row in rows if int(row["expected_rejection"])
        ),
        "llm_calls": agent.metrics.llm_calls,
        "promoted_machines": len(promoted),
        "rejections": len(rejected),
        "induced_machine_types": [audit.candidate_intent_type for audit in promoted],
        "final_state": state,
        "state_mutations_verified": state
        == {
            "bluetooth": True,
            "dark_mode": False,
            "privacy_mode": True,
            "roaming_data": True,
            "auto_sync": False,
        },
    }

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "episode_metrics.csv", rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote dynamic affordance generalization outputs to {output_dir}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
