from __future__ import annotations

import ast
import csv
import inspect
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOL_SANDBOX = ROOT / "third_party" / "ToolSandbox-main"
for path in (SRC, TOOL_SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pctu_pilot.appworld_agents import build_appworld_intent_machines  # noqa: E402
from pctu_pilot.toolsandbox_agents import RiskAdaptiveToolSandboxAgent  # noqa: E402


TOOL_SANDBOX_INSUFFICIENT = (
    ROOT
    / "results/toolsandbox_qwen25_3b_rave2_insufficient_compare_fixed2/20260501_153424/summary.csv"
)
APPWORLD_FULL168 = (
    ROOT
    / "results/appworld_rave_official_test_normal_full168_trip_note_debts_20260524/20260524_225648/episode_metrics.csv"
)
APPWORLD_STATIC_COVERAGE = ROOT / "results/appworld_static_coverage/20260524/summary.json"
MINISTORE_PCTU = ROOT / "results/real_llm_ministore_qwen25_3b_rave_tpc2_v2.csv"
TOOLSANDBOX_GUARDRAIL = (
    ROOT
    / "results/toolsandbox_pctu_insufficient_deepseek/20260524_211028/summary.csv"
)
TOOLSANDBOX_DEEPSEEK_INSUFFICIENT = (
    ROOT
    / "results/frontier_toolsandbox_replication_deepseek/deepseek-chat_insufficient/20260504_041631/summary.csv"
)
APPWORLD_CHALLENGE_TEXT = ROOT / "paper/rave_intent_compiled_verified_execution_arr.tex"
OUTPUT_DIR = ROOT / "results/icve_review_strengthening/20260524"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    appworld_rows = read_csv_dicts(APPWORLD_FULL168)
    machine_rows = machine_development_rows(appworld_rows)
    summary = {
        "guardrail_baseline": guardrail_baseline(),
        "toolsandbox_guardrail_representative": toolsandbox_guardrail_representative(),
        "failure_mode_shift": failure_mode_shift(),
        "coverage_risk": coverage_risk(appworld_rows),
        "static_instruction_coverage": static_instruction_coverage(),
        "machine_coverage_cost": machine_coverage_cost(appworld_rows, machine_rows),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(OUTPUT_DIR / "machine_development_costs.csv", machine_rows)
    write_markdown(OUTPUT_DIR / "README.md", summary)
    write_machine_markdown(OUTPUT_DIR / "machine_development_costs.md", machine_rows, summary)
    print(json.dumps(summary, indent=2))


def guardrail_baseline() -> dict[str, Any]:
    rows = read_csv_dicts(MINISTORE_PCTU)
    by_method: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_method.setdefault(row["method"], []).append(row)

    def aggregate(method: str) -> dict[str, float]:
        subset = by_method[method]
        return {
            "n": float(len(subset)),
            "success": mean_int(subset, "success"),
            "goal_achieved": mean_int(subset, "goal_achieved"),
            "invalid": mean_int(subset, "invalid_tool_calls"),
            "unsafe": mean_int(subset, "unsafe_changes"),
            "verifier_rejections": mean_int(subset, "verifier_rejections"),
            "llm_calls": mean_int(subset, "llm_calls"),
            "token_proxy": mean_int(subset, "token_proxy"),
        }

    return {
        "benchmark": "MiniStore real-LLM diagnostic, Qwen2.5-3B",
        "baseline_definition": (
            "PCTU is the ReAct+schema/proof/verifier guardrail baseline: the model "
            "still owns the action loop, but every mutating action must include a JSON "
            "contract with evidence and expected postconditions, and a runtime verifier "
            "rejects schema, grounding, precondition, and postcondition failures."
        ),
        "react": aggregate("Real LLM ReAct"),
        "pctu_guardrail": aggregate("Real LLM Proof-Carrying Tool Use"),
        "icve": aggregate("Real LLM Risk-Adaptive Verified Execution"),
    }


def toolsandbox_guardrail_representative() -> dict[str, Any]:
    rows = read_csv_dicts(TOOLSANDBOX_GUARDRAIL) + read_csv_dicts(TOOLSANDBOX_DEEPSEEK_INSUFFICIENT)
    by_method = {row["method"]: row for row in rows}

    def metrics(name: str) -> dict[str, float]:
        row = by_method[name]
        return {
            "n": float(row["episodes"]),
            "success": float(row["success_rate"]),
            "unsafe": float(row["unsafe_state_changes_per_task"]),
            "invalid": float(row["invalid_tool_calls_per_task"]),
            "verifier_rejections": float(row["verifier_rejections_per_task"]),
            "repair_calls": float(row["repair_calls_per_task"]),
            "llm_calls": float(row["llm_calls_per_task"]),
            "token_proxy": float(row["token_proxy_per_task"]),
        }

    return {
        "benchmark": "ToolSandbox insufficient-information full suite, DeepSeek-chat",
        "n": int(float(by_method["ToolSandbox ReAct"]["episodes"])),
        "react": metrics("ToolSandbox ReAct"),
        "pctu_guardrail": metrics("ToolSandbox PCTU"),
        "icve": metrics("ToolSandbox RAVE"),
    }


def failure_mode_shift() -> dict[str, Any]:
    rows = read_csv_dicts(TOOL_SANDBOX_INSUFFICIENT)
    by_method = {row["method"]: row for row in rows}

    def row_metrics(name: str) -> dict[str, float]:
        row = by_method[name]
        return {
            "success": float(row["success_rate"]),
            "unsafe": float(row["unsafe_state_changes_per_task"]),
            "invalid": float(row["invalid_tool_calls_per_task"]),
            "other_or_incomplete": max(
                0.0,
                1.0 - float(row["success_rate"]) - float(row["unsafe_state_changes_per_task"]),
            ),
        }

    react = row_metrics("ToolSandbox ReAct")
    icve = row_metrics("ToolSandbox RAVE")
    no_abstention = row_metrics("ToolSandbox RAVE - no abstention verifier")
    return {
        "benchmark": "ToolSandbox insufficient-information, Qwen2.5-3B",
        "n": int(float(by_method["ToolSandbox ReAct"]["episodes"])),
        "react": react,
        "icve": icve,
        "no_abstention": no_abstention,
        "unsafe_reduction_react_to_icve": react["unsafe"] - icve["unsafe"],
        "invalid_reduction_react_to_icve": react["invalid"] - icve["invalid"],
    }


def coverage_risk(rows: list[dict[str, str]]) -> dict[str, Any]:
    total = len(rows)
    supported = sum(int(row["supported"]) for row in rows)
    success = sum(int(row["success"]) for row in rows)
    unsupported = total - supported
    unsafe = sum(int(row["unsafe_state_changes"]) for row in rows)
    invalid = sum(int(row["invalid_tool_calls"]) for row in rows)
    intent_counts: dict[str, int] = {}
    for row in rows:
        if int(row["supported"]):
            intent_counts[row["intent_type"]] = intent_counts.get(row["intent_type"], 0) + 1
    top_intents = sorted(intent_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    return {
        "benchmark": "AppWorld local test_normal.txt file-level diagnostic",
        "tasks": total,
        "supported": supported,
        "unsupported_safe_no_action": unsupported,
        "overall_success": success,
        "supported_success": sum(int(row["success"]) for row in rows if int(row["supported"])),
        "unsafe_state_changes": unsafe,
        "invalid_tool_calls": invalid,
        "supported_rate": supported / total if total else 0.0,
        "overall_success_rate": success / total if total else 0.0,
        "supported_success_rate": (
            sum(int(row["success"]) for row in rows if int(row["supported"])) / supported
            if supported
            else 0.0
        ),
        "top_supported_intents": top_intents,
        "challenge_prefix": {
            "tasks": 24,
            "solved_before_new_amazon_machines": 3,
            "solved_after_two_saved_list_machines": 12,
            "unsupported_safe_no_action": 12,
            "unsafe_state_changes": 0,
        },
    }


def static_instruction_coverage() -> dict[str, Any]:
    summary = json.loads(APPWORLD_STATIC_COVERAGE.read_text(encoding="utf-8"))
    return {
        "benchmark": "AppWorld public-instruction static compile audit",
        "not_a_success_or_leaderboard_metric": bool(
            summary["not_a_success_or_leaderboard_metric"]
        ),
        "registered_appworld_machines": int(summary["registered_appworld_machines"]),
        "total_tasks": int(summary["total_tasks"]),
        "overall": summary["overall"],
        "test_normal": summary["by_split"]["test_normal"],
        "test_challenge": summary["by_split"]["test_challenge"],
        "top_unsupported_buckets": summary["top_unsupported_buckets"],
    }


def machine_coverage_cost(
    appworld_rows: list[dict[str, str]],
    machine_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    toolsandbox_agent = RiskAdaptiveToolSandboxAgent(client=_NoopClient())
    toolsandbox_machines = toolsandbox_agent._build_intent_machines()
    appworld_machines = build_appworld_intent_machines()
    appworld_intents = {row["intent_type"] for row in appworld_rows if int(row["supported"])}

    costs_for_supported = [row for row in machine_rows if row["covered_tasks"] > 0]
    return {
        "toolsandbox_static_machines": len(toolsandbox_machines),
        "appworld_static_machines": len(appworld_machines),
        "appworld_machines_used_in_full168": len(appworld_intents),
        "appworld_supported_tasks": sum(int(row["supported"]) for row in appworld_rows),
        "appworld_tasks_per_used_machine": (
            sum(int(row["supported"]) for row in appworld_rows) / len(appworld_intents)
            if appworld_intents
            else 0.0
        ),
        "appworld_handler_loc_median": median([cost["handler_loc"] for cost in costs_for_supported]),
        "appworld_handler_loc_mean": statistics.mean(
            [cost["handler_loc"] for cost in costs_for_supported]
        )
        if costs_for_supported
        else 0.0,
        "appworld_compiler_loc_median": median([cost["compiler_loc"] for cost in costs_for_supported]),
        "appworld_total_loc_median": median([cost["total_loc"] for cost in costs_for_supported]),
        "appworld_slots_median": median([cost["slots"] for cost in costs_for_supported]),
        "appworld_slots_mean": statistics.mean([cost["slots"] for cost in costs_for_supported])
        if costs_for_supported
        else 0.0,
        "adaptation_time_status": "not_recorded_for_historical_machines",
        "top_tasks_per_machine": coverage_top(appworld_rows),
    }


def machine_development_rows(appworld_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    coverage: dict[str, dict[str, int]] = {}
    for row in appworld_rows:
        intent = row["intent_type"]
        stats = coverage.setdefault(
            intent,
            {
                "covered_tasks": 0,
                "successful_tasks": 0,
                "unsafe_state_changes": 0,
                "invalid_tool_calls": 0,
            },
        )
        if int(row["supported"]):
            stats["covered_tasks"] += 1
            stats["successful_tasks"] += int(row["success"])
            stats["unsafe_state_changes"] += int(row["unsafe_state_changes"])
            stats["invalid_tool_calls"] += int(row["invalid_tool_calls"])

    rows = []
    for machine in build_appworld_intent_machines():
        handler_source = source_for(machine.handler)
        compiler_source = source_for(machine.compiler)
        api_namespaces = sorted(set(re.findall(r"\bapis\.([A-Za-z_][A-Za-z0-9_]*)\.", handler_source)))
        stats = coverage.get(machine.schema.intent_type, {})
        slots = [slot.name for slot in machine.schema.slots]
        rows.append(
            {
                "intent_type": machine.schema.intent_type,
                "slots": len(slots),
                "slot_names": ",".join(slots) if slots else "none",
                "compiler_loc": nonblank_loc(compiler_source),
                "handler_loc": nonblank_loc(handler_source),
                "total_loc": nonblank_loc(compiler_source) + nonblank_loc(handler_source),
                "covered_tasks": int(stats.get("covered_tasks", 0)),
                "successful_tasks": int(stats.get("successful_tasks", 0)),
                "unsafe_state_changes": int(stats.get("unsafe_state_changes", 0)),
                "invalid_tool_calls": int(stats.get("invalid_tool_calls", 0)),
                "shared_api_namespaces": ",".join(api_namespaces) if api_namespaces else "none",
                "shared_runtime_components": "schema,compiler,handler,ledger,policy",
                "adaptation_time": "not_recorded",
            }
        )
    return sorted(rows, key=lambda row: (-row["covered_tasks"], row["intent_type"]))


def machine_costs(machines: list[Any]) -> list[dict[str, Any]]:
    costs = []
    for machine in machines:
        handler_source = source_for(machine.handler)
        costs.append(
            {
                "intent_type": machine.schema.intent_type,
                "slots": len(machine.schema.slots),
                "handler_loc": nonblank_loc(handler_source),
            }
        )
    return costs


def source_for(fn: Any) -> str:
    try:
        return inspect.getsource(fn)
    except OSError:
        return ""


def nonblank_loc(source: str) -> int:
    return sum(
        1
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def coverage_top(rows: list[dict[str, str]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        if int(row["supported"]):
            counts[row["intent_type"]] = counts.get(row["intent_type"], 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def median(values: list[int | float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def mean_int(rows: list[dict[str, str]], key: str) -> float:
    return statistics.mean(int(row[key]) for row in rows) if rows else 0.0


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    guardrail = summary["guardrail_baseline"]
    ts_guardrail = summary["toolsandbox_guardrail_representative"]
    failure = summary["failure_mode_shift"]
    coverage = summary["coverage_risk"]
    static_coverage = summary["static_instruction_coverage"]
    cost = summary["machine_coverage_cost"]
    text = f"""# ICVE Review-Strengthening Analysis

## Guardrail Baseline

On the MiniStore real-LLM diagnostic, PCTU instantiates a stronger ReAct+schema/proof/
verifier guardrail baseline: the model still owns the action loop, but every mutating
action must carry evidence and expected postconditions checked by a runtime verifier.
ReAct has success={guardrail['react']['success']:.4f}, invalid/tool={guardrail['react']['invalid']:.4f},
unsafe={guardrail['react']['unsafe']:.4f}. PCTU reduces invalid and unsafe outcomes to
{guardrail['pctu_guardrail']['invalid']:.4f}/{guardrail['pctu_guardrail']['unsafe']:.4f},
but reaches only success={guardrail['pctu_guardrail']['success']:.4f} with
{guardrail['pctu_guardrail']['llm_calls']:.2f} LLM calls/task and
{guardrail['pctu_guardrail']['token_proxy']:.1f} token proxy/task. ICVE reaches
success={guardrail['icve']['success']:.4f} with {guardrail['icve']['llm_calls']:.2f}
LLM calls/task and {guardrail['icve']['token_proxy']:.1f} token proxy/task.

On the full 28-scenario DeepSeek-chat ToolSandbox insufficient-information suite, ReAct
reaches success={ts_guardrail['react']['success']:.4f} with
unsafe={ts_guardrail['react']['unsafe']:.4f} and invalid/tool={ts_guardrail['react']['invalid']:.4f}.
PCTU reaches success={ts_guardrail['pctu_guardrail']['success']:.4f} and
unsafe={ts_guardrail['pctu_guardrail']['unsafe']:.4f}, but still records
invalid/tool={ts_guardrail['pctu_guardrail']['invalid']:.4f},
verifier_rejections={ts_guardrail['pctu_guardrail']['verifier_rejections']:.2f},
and {ts_guardrail['pctu_guardrail']['llm_calls']:.2f} LLM calls/task. ICVE reaches
success={ts_guardrail['icve']['success']:.4f} with invalid/tool={ts_guardrail['icve']['invalid']:.4f},
unsafe={ts_guardrail['icve']['unsafe']:.4f}, and {ts_guardrail['icve']['llm_calls']:.2f}
agent LLM calls/task.

## Failure-Mode Shift

On ToolSandbox insufficient-information tasks (`n={failure['n']}`), ReAct records
success={failure['react']['success']:.4f}, unsafe={failure['react']['unsafe']:.4f}, and
invalid/tool={failure['react']['invalid']:.4f}. ICVE records
success={failure['icve']['success']:.4f}, unsafe={failure['icve']['unsafe']:.4f}, and
invalid/tool={failure['icve']['invalid']:.4f}. Removing abstention keeps success at
{failure['no_abstention']['success']:.4f} but restores unsafe={failure['no_abstention']['unsafe']:.4f}.

## Coverage-Risk Tradeoff

On the local AppWorld `test_normal.txt` execution diagnostic, deterministic ICVE supports {coverage['supported']}
of {coverage['tasks']} tasks and succeeds on {coverage['overall_success']} overall
({coverage['supported_success']} of {coverage['supported']} supported). The remaining
{coverage['unsupported_safe_no_action']} tasks are unsupported safe no-action outcomes;
unsafe state changes are {coverage['unsafe_state_changes']} and invalid tool calls are
{coverage['invalid_tool_calls']}. The `test_challenge` prefix is a negative-control
diagnostic: after adding two conservative saved-list machines, 12/24 solve, 12/24 remain
unsupported no-action, and unsafe state changes remain 0.

The static public-instruction audit covers all local AppWorld `test_normal.txt` and
`test_challenge.txt` IDs without executing tools or loading ground truth. It compiles
{static_coverage['test_normal']['dispatchable']}/{static_coverage['test_normal']['tasks']}
`test_normal` instructions and
{static_coverage['test_challenge']['dispatchable']}/{static_coverage['test_challenge']['tasks']}
`test_challenge` instructions to complete intent frames. Unsupported `test_challenge`
rows cluster mainly in {static_coverage['top_unsupported_buckets'][0][0]}
({static_coverage['top_unsupported_buckets'][0][1]} tasks) and
{static_coverage['top_unsupported_buckets'][1][0]}
({static_coverage['top_unsupported_buckets'][1][1]} tasks), making the coverage boundary
auditable rather than implicit.

## Machine Coverage and Development Cost

The ToolSandbox binding has {cost['toolsandbox_static_machines']} static intent machines.
The AppWorld binding has {cost['appworld_static_machines']} static intent machines; the
full168 diagnostic uses {cost['appworld_machines_used_in_full168']} machine types for
{cost['appworld_supported_tasks']} supported tasks, or
{cost['appworld_tasks_per_used_machine']:.2f} tasks per used machine. For used AppWorld
machines, median compiler LOC is {cost['appworld_compiler_loc_median']:.1f}, median
handler LOC is {cost['appworld_handler_loc_median']:.1f}, median total LOC is
{cost['appworld_total_loc_median']:.1f}, and median slot count is
{cost['appworld_slots_median']:.1f}. Historical adaptation time was not recorded, so the
per-machine table marks `adaptation_time=not_recorded` and uses LOC/coverage as auditable
cost proxies.
"""
    path.write_text(text, encoding="utf-8")


def write_machine_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    cost = summary["machine_coverage_cost"]
    lines = [
        "# AppWorld Machine Development-Cost Table",
        "",
        "This table is generated from `src/pctu_pilot/appworld_agents.py` and the local",
        "`test_normal.txt` diagnostic. It records every registered AppWorld `IntentMachine`.",
        "Historical wall-clock adaptation time was not logged, so the field is explicitly",
        "`not_recorded`; compiler/handler LOC, slots, shared API namespaces, and covered task",
        "counts are reproducible proxies for development cost and reuse.",
        "",
        f"- Registered AppWorld machines: {cost['appworld_static_machines']}",
        f"- Used by full168 supported tasks: {cost['appworld_machines_used_in_full168']}",
        f"- Supported tasks: {cost['appworld_supported_tasks']}",
        f"- Tasks per used machine: {cost['appworld_tasks_per_used_machine']:.2f}",
        f"- Median slots / compiler LOC / handler LOC / total LOC: "
        f"{cost['appworld_slots_median']:.1f} / {cost['appworld_compiler_loc_median']:.1f} / "
        f"{cost['appworld_handler_loc_median']:.1f} / {cost['appworld_total_loc_median']:.1f}",
        "",
        "| intent_type | slots | compiler LOC | handler LOC | covered tasks | shared APIs | adaptation time |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {intent_type} | {slots} | {compiler_loc} | {handler_loc} | "
            "{covered_tasks} | {shared_api_namespaces} | {adaptation_time} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class _NoopClient:
    def chat(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("No model calls are needed for machine-cost summarization")


if __name__ == "__main__":
    main()
