from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import json
import os
import statistics
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOL_SANDBOX = ROOT / "third_party" / "ToolSandbox-main"
for path in (SRC, TOOL_SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pctu_pilot.llm_client import OpenAICompatibleClient  # noqa: E402


DEFAULT_SCENARIOS = [
    "cellular_off",
    "get_cellular",
    "wifi_off",
    "get_wifi",
    "search_phone_number_with_name",
    "search_name_with_relationship",
    "search_relationship_with_phone_number",
    "add_contact_with_name_and_phone_number",
    "remove_contact_with_id",
    "update_contact_with_id_and_phone_number",
    "search_sender_phone_number_with_content",
    "send_message_with_phone_number_and_content",
    "search_message_with_recency_latest",
    "search_message_with_recency_latest_alt",
    "search_message_with_recency_oldest",
    "search_message_with_recency_oldest_alt",
    "remove_contact_by_phone",
    "remove_contact_by_phone_alt",
    "remove_contact_by_phone_ambiguous",
    "remove_contact_by_phone_ambiguous_alt",
    "turn_on_wifi_low_battery_mode",
    "turn_on_wifi_low_battery_mode_implicit",
    "turn_on_cellular_low_battery_mode",
    "turn_on_cellular_low_battery_mode_implicit",
    "turn_on_location_low_battery_mode",
    "turn_on_location_low_battery_mode_implicit",
    "send_message_with_contact_content_cellular_off",
    "send_message_with_contact_content_cellular_off_alt",
    "update_contact_relationship_with_relationship",
    "update_contact_relationship_with_relationship_alt",
]


RAVE_ABLATION_METHODS = {
    "rave_no_intent": {
        "name": "ToolSandbox RAVE - no intent compiler",
        "options": {"enable_intent_compiler": False},
    },
    "rave_no_normalizer": {
        "name": "ToolSandbox RAVE - no argument normalizer",
        "options": {"enable_argument_normalizer": False},
    },
    "rave_no_repair": {
        "name": "ToolSandbox RAVE - no precondition repair",
        "options": {"enable_precondition_repair": False},
    },
    "rave_no_completion": {
        "name": "ToolSandbox RAVE - no completion detector",
        "options": {"enable_completion_detector": False},
    },
    "rave_no_rave2_dsl": {
        "name": "ToolSandbox RAVE - no RAVE-2 DSL",
        "options": {"enable_rave2_dsl": False},
    },
    "rave_no_abstention": {
        "name": "ToolSandbox RAVE - no abstention verifier",
        "options": {"enable_abstention_verifier": False},
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a small ToolSandbox kill-criteria experiment comparing plain ReAct "
            "against RAVE / Intent-Compiled Verified Execution with a real "
            "OpenAI-compatible LLM."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--api-key", default=os.environ.get("FRONTIER_API_KEY", "not-needed"))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--max-messages", type=int, default=30)
    parser.add_argument("--max-scenarios", type=int, default=30)
    parser.add_argument(
        "--scenario-suite",
        default="core30",
        choices=[
            "core30",
            "single_turn_no_distraction",
            "multi_turn_no_distraction",
            "insufficient_no_distraction",
            "expanded_no_distraction",
            "distraction_sample",
            "all",
        ],
        help="Scenario suite to run when --scenarios is not supplied.",
    )
    parser.add_argument("--scenarios", nargs="*", default=None)
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["react", "rave"],
        choices=["react", "pctu", "rave", *RAVE_ABLATION_METHODS.keys()],
    )
    parser.add_argument(
        "--user-mode",
        default="passive",
        choices=["passive", "local-llm", "hidden-task"],
        help="Use local-llm for multi-turn or insufficient-information scenarios.",
    )
    parser.add_argument("--user-max-tokens", type=int, default=256)
    parser.add_argument("--preferred-tool-backend", default="DEFAULT")
    parser.add_argument(
        "--rapidapi-fixture",
        default="auto",
        choices=["auto", "on", "off"],
        help=(
            "Use a deterministic offline fixture for ToolSandbox RapidAPI-backed tools. "
            "'auto' enables it only when RAPID_API_KEY is absent."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="results/toolsandbox_kill_criteria",
        help="Base directory for ToolSandbox trajectories and summaries.",
    )
    parser.add_argument("--healthcheck-only", action="store_true")
    parser.add_argument("--min-invalid-reduction", type=float, default=0.25)
    parser.add_argument("--min-success-delta", type=float, default=0.05)
    parser.add_argument("--max-cost-multiplier", type=float, default=2.0)
    args = parser.parse_args()

    client = OpenAICompatibleClient(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        timeout_s=180,
    )
    if not client.healthcheck():
        raise SystemExit(
            "No OpenAI-compatible server responded. Start LM Studio, llama.cpp server, "
            "Ollama OpenAI API, or vLLM, then rerun with --base-url and --model."
        )
    if args.healthcheck_only:
        print(f"Server is reachable: {args.base_url}")
        return

    try:
        imports = import_toolsandbox_runtime()
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"Missing ToolSandbox dependency: {exc.name}. Install ToolSandbox dependencies "
            "in a Python 3.10/3.11 environment, then rerun this script."
        ) from exc
    fixture_enabled = should_enable_rapidapi_fixture(args.rapidapi_fixture)
    if fixture_enabled:
        apply_offline_rapidapi_fixture()

    selected_names = select_scenario_names(args, imports)
    if args.max_scenarios > 0:
        selected_names = selected_names[: args.max_scenarios]
    scenarios = imports["resolve_scenarios"](
        desired_scenario_names=selected_names,
        preferred_tool_backend=imports["ToolBackend"][args.preferred_tool_backend],
    )

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for method in args.methods:
        for scenario_name, scenario in scenarios.items():
            rows.append(
                run_one(
                    imports=imports,
                    client=client,
                    method=method,
                    scenario_name=scenario_name,
                    scenario=scenario,
                    output_dir=output_dir,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    max_messages=args.max_messages,
                    user_mode=args.user_mode,
                    user_max_tokens=args.user_max_tokens,
                )
            )
            print(
                f"{rows[-1]['method']} {scenario_name}: "
                f"similarity={rows[-1]['similarity']} "
                f"invalid={rows[-1]['invalid_tool_calls']} "
                f"rejections={rows[-1]['verifier_rejections']}"
            )

    summary = summarize(rows)
    verdict = judge_kill_criteria(
        summary,
        min_invalid_reduction=args.min_invalid_reduction,
        min_success_delta=args.min_success_delta,
        max_cost_multiplier=args.max_cost_multiplier,
    )

    write_csv(output_dir / "episode_metrics.csv", rows)
    write_csv(output_dir / "summary.csv", summary)
    write_markdown_table(output_dir / "summary.md", summary, "ToolSandbox Kill-Criteria Summary")
    write_verdict(output_dir / "kill_criteria.md", verdict, summary, args)
    write_metadata(output_dir / "metadata.json", args, selected_names, fixture_enabled)

    print(f"Wrote ToolSandbox kill-criteria outputs to {output_dir}")
    print(verdict["decision"])


def import_toolsandbox_runtime() -> dict[str, Any]:
    from pctu_pilot.toolsandbox_agents import (  # noqa: PLC0415
        JsonToolUseAgent,
        HiddenTaskUser,
        LocalOpenAIUser,
        PassiveUser,
        ProofCarryingToolSandboxAgent,
        RaveRuntimeOptions,
        RiskAdaptiveToolSandboxAgent,
    )
    from tool_sandbox.cli.utils import resolve_scenarios  # noqa: PLC0415
    from tool_sandbox.common.execution_context import (  # noqa: PLC0415
        DatabaseNamespace,
        RoleType,
        get_current_context,
    )
    from tool_sandbox.common.tool_discovery import ToolBackend  # noqa: PLC0415
    from tool_sandbox.roles.execution_environment import ExecutionEnvironment  # noqa: PLC0415

    return {
        "JsonToolUseAgent": JsonToolUseAgent,
        "HiddenTaskUser": HiddenTaskUser,
        "LocalOpenAIUser": LocalOpenAIUser,
        "PassiveUser": PassiveUser,
        "ProofCarryingToolSandboxAgent": ProofCarryingToolSandboxAgent,
        "RaveRuntimeOptions": RaveRuntimeOptions,
        "RiskAdaptiveToolSandboxAgent": RiskAdaptiveToolSandboxAgent,
        "resolve_scenarios": resolve_scenarios,
        "DatabaseNamespace": DatabaseNamespace,
        "ExecutionEnvironment": ExecutionEnvironment,
        "RoleType": RoleType,
        "ToolBackend": ToolBackend,
        "get_current_context": get_current_context,
    }


def should_enable_rapidapi_fixture(mode: str) -> bool:
    if mode == "on":
        return True
    if mode == "off":
        return False
    return "RAPID_API_KEY" not in os.environ


def apply_offline_rapidapi_fixture() -> None:
    """Patch ToolSandbox RapidAPI-backed tools with deterministic local responses.

    The public ToolSandbox scenarios include RapidAPI-backed tools, but many local
    research machines do not have a RapidAPI key. This fixture keeps the benchmark
    tool signatures and state transitions intact while replacing only the external
    HTTP payloads with stable responses.
    """

    from tool_sandbox.tools import rapid_api_search_tools  # noqa: PLC0415

    def fixture(url: str, params: dict[str, Any], headers: dict[str, Any]) -> dict[str, Any]:
        host = str(headers.get("X-RapidAPI-Host") or "")
        if host == "trueway-geocoding.p.rapidapi.com":
            return {
                "results": [
                    {
                        "address": "Apple Park 1 Apple Park Way Cupertino, CA 95014 United States",
                    }
                ]
            }

        if host == "maps-data.p.rapidapi.com":
            query = str(params.get("query") or "").casefold()
            if "mckinley" in query:
                return {
                    "data": [
                        {
                            "name": "Whole Foods Market",
                            "address": "777 The Alameda, San Jose, CA 95126",
                            "phone_number": "+14089962055",
                            "latitude": 37.3738083,
                            "longitude": -122.0314225,
                            "business_id": "fixture-whole-foods-mckinley",
                            "place_id": "fixture-whole-foods-mckinley",
                            "place_link": "",
                            "verified": True,
                            "photos": [],
                        }
                    ]
                }
            if "whole foods" in query:
                return {
                    "data": [
                        {
                            "name": "Whole Foods Market",
                            "address": "20955 Stevens Creek Blvd, Cupertino, CA 95014",
                            "phone_number": "+14089962055",
                            "latitude": 37.323498,
                            "longitude": -122.039665,
                            "business_id": "fixture-whole-foods",
                            "place_id": "fixture-whole-foods",
                            "place_link": "",
                            "verified": True,
                            "photos": [],
                        }
                    ]
                }
            if "apple park" in query:
                return {
                    "data": [
                        {
                            "name": "Apple Park",
                            "address": "1 Apple Park Way, Cupertino, CA 95014",
                            "phone_number": "+14089961010",
                            "latitude": 37.334606,
                            "longitude": -122.009102,
                            "business_id": "fixture-apple-park",
                            "place_id": "fixture-apple-park",
                            "place_link": "",
                            "verified": True,
                            "photos": [],
                        }
                    ]
                }
            return {
                "data": [
                    {
                        "name": str(params.get("query") or "Location"),
                        "address": "Cupertino, CA, United States",
                        "latitude": float(params.get("lat") or 37.334606),
                        "longitude": float(params.get("lng") or -122.009102),
                    }
                ]
            }

        if host == "weatherapi-com.p.rapidapi.com":
            forecast_days = []
            for index in range(max(2, int(params.get("days") or 1))):
                forecast_days.append(
                    {
                        "day": {
                            "maxtemp_c": 21.0 + index,
                            "mintemp_c": 5.0 + index,
                            "avgtemp_c": 13.0 + index,
                            "maxwind_kph": 18.0 + index,
                            "avgvis_km": 16.0,
                            "avghumidity": 35 + index,
                            "condition": {"text": "Sunny"},
                        },
                        "astro": {
                            "sunrise": "06:15 AM",
                            "sunset": "06:05 PM",
                        },
                    }
                )
            return {
                "location": {
                    "name": "Fixture Location",
                    "region": "California",
                    "country": "United States",
                    "timezone": "America/Los_Angeles",
                },
                "current": {
                    "temp_c": 17.0,
                    "feelslike_c": 16.0,
                    "vis_km": 16.0,
                    "wind_kph": 8.0,
                    "pressure_mb": 1012.0,
                },
                "forecast": {"forecastday": forecast_days},
            }

        if host == "real-time-finance-data.p.rapidapi.com":
            query = str(params.get("query") or "Apple")
            symbol = "AAPL:NASDAQ" if "apple" in query.casefold() or query.casefold() == "aapl" else "UNKNOWN:NASDAQ"
            return {
                "data": {
                    "stock": [
                        {
                            "name": "Apple Inc.",
                            "symbol": symbol,
                            "exchange": "NASDAQ",
                            "price": 180.0,
                            "change": 0.0,
                            "percent_change": 0.0,
                            "currency": "USD",
                        }
                    ]
                }
            }

        if host == "currency-converter18.p.rapidapi.com":
            amount = float(params.get("amount") or 0)
            from_code = str(params.get("from") or "").upper()
            to_code = str(params.get("to") or "").upper()
            rates = {
                ("USD", "CNY"): 7.2,
                ("CNY", "USD"): 1 / 7.2,
                ("USD", "EUR"): 0.92,
                ("EUR", "USD"): 1.08,
            }
            return {"result": {"convertedAmount": amount * rates.get((from_code, to_code), 1.0)}}

        raise RuntimeError(f"No offline RapidAPI fixture for host={host!r} url={url!r}")

    rapid_api_search_tools.rapid_api_get_request = fixture


def select_scenario_names(args: argparse.Namespace, imports: dict[str, Any]) -> list[str]:
    if args.scenarios is not None:
        return list(args.scenarios)
    if args.scenario_suite == "core30":
        return list(DEFAULT_SCENARIOS)

    all_scenarios = imports["resolve_scenarios"](
        desired_scenario_names=None,
        preferred_tool_backend=imports["ToolBackend"][args.preferred_tool_backend],
    )

    def category_names(scenario: Any) -> set[str]:
        return {str(category) for category in scenario.categories}

    def has_all(scenario: Any, *required: str) -> bool:
        categories = category_names(scenario)
        return all(item in categories for item in required)

    if args.scenario_suite == "single_turn_no_distraction":
        return [
            name
            for name, scenario in all_scenarios.items()
            if has_all(scenario, "SINGLE_USER_TURN", "NO_DISTRACTION_TOOLS")
        ]
    if args.scenario_suite == "multi_turn_no_distraction":
        return [
            name
            for name, scenario in all_scenarios.items()
            if has_all(scenario, "MULTIPLE_USER_TURN", "NO_DISTRACTION_TOOLS")
        ]
    if args.scenario_suite == "insufficient_no_distraction":
        return [
            name
            for name, scenario in all_scenarios.items()
            if has_all(scenario, "INSUFFICIENT_INFORMATION", "NO_DISTRACTION_TOOLS")
        ]
    if args.scenario_suite == "expanded_no_distraction":
        return [
            name
            for name, scenario in all_scenarios.items()
            if "NO_DISTRACTION_TOOLS" in category_names(scenario)
        ]
    if args.scenario_suite == "distraction_sample":
        return [
            name
            for name in all_scenarios
            if name.endswith("_3_distraction_tools") and not name.endswith("_tool_description_scrambled")
        ]
    if args.scenario_suite == "all":
        return list(all_scenarios)
    raise ValueError(args.scenario_suite)


def run_one(
    *,
    imports: dict[str, Any],
    client: OpenAICompatibleClient,
    method: str,
    scenario_name: str,
    scenario: Any,
    output_dir: Path,
    temperature: float,
    max_tokens: int,
    max_messages: int,
    user_mode: str,
    user_max_tokens: int,
) -> dict[str, Any]:
    RoleType = imports["RoleType"]
    scenario = copy.deepcopy(scenario)
    scenario.max_messages = max_messages
    if method == "react":
        agent = imports["JsonToolUseAgent"](
            client=client,
            method_name="ToolSandbox ReAct",
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif method == "pctu":
        agent = imports["ProofCarryingToolSandboxAgent"](
            client=client,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif method == "rave":
        agent = imports["RiskAdaptiveToolSandboxAgent"](
            client=client,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif method in RAVE_ABLATION_METHODS:
        spec = RAVE_ABLATION_METHODS[method]
        agent = imports["RiskAdaptiveToolSandboxAgent"](
            client=client,
            method_name=spec["name"],
            options=imports["RaveRuntimeOptions"](**spec["options"]),
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        raise ValueError(method)

    if user_mode == "local-llm":
        user = imports["LocalOpenAIUser"](
            client=client,
            model_name=f"{agent.model_name} user simulator",
            temperature=temperature,
            max_tokens=user_max_tokens,
        )
    elif user_mode == "hidden-task":
        user = imports["HiddenTaskUser"]()
    elif user_mode == "passive":
        user = imports["PassiveUser"]()
    else:
        raise ValueError(user_mode)

    roles = {
        RoleType.USER: user,
        RoleType.EXECUTION_ENVIRONMENT: imports["ExecutionEnvironment"](),
        RoleType.AGENT: agent,
    }
    method_dir = output_dir / method
    method_dir.mkdir(parents=True, exist_ok=True)

    exception_type = ""
    traceback_text = ""
    evaluation = None
    ending_context = None
    try:
        result = scenario.play_and_evaluate(
            roles=roles,
            output_directory=method_dir,
            scenario_name=scenario_name,
        )
        evaluation = result.evaluation_result
        ending_context = result.ending_context
    except Exception as exc:  # noqa: BLE001
        exception_type = type(exc).__name__
        traceback_text = traceback.format_exc()
        try:
            ending_context = imports["get_current_context"]()
        except Exception:  # noqa: BLE001
            ending_context = None
    finally:
        for role in roles.values():
            role.teardown()

    tool_stats = count_tool_stats(imports, ending_context) if ending_context is not None else {}
    metrics = agent.metrics
    user_metrics = getattr(user, "metrics", None)
    categories = [str(category) for category in scenario.categories]
    return {
        "method": agent.model_name,
        "scenario": scenario_name,
        "categories": ";".join(categories),
        "success": int(evaluation is not None and evaluation.similarity >= 0.999),
        "similarity": round(float(evaluation.similarity), 4) if evaluation else 0.0,
        "milestone_similarity": round(float(evaluation.milestone_similarity), 4) if evaluation else 0.0,
        "minefield_similarity": round(float(evaluation.minefield_similarity), 4) if evaluation else 0.0,
        "unsafe_state_changes": int(evaluation is not None and evaluation.minefield_similarity > 0),
        "turn_count": int(evaluation.turn_count) if evaluation else max_messages,
        "invalid_tool_calls": int(tool_stats.get("invalid_tool_calls", 0)),
        "tool_calls": int(tool_stats.get("tool_calls", 0)),
        "llm_calls": metrics.llm_calls,
        "token_proxy": metrics.token_proxy,
        "user_llm_calls": int(getattr(user_metrics, "llm_calls", 0) or 0),
        "user_token_proxy": int(getattr(user_metrics, "token_proxy", 0) or 0),
        "verifier_rejections": metrics.verifier_rejections,
        "repair_calls": metrics.repair_calls,
        "parse_errors": metrics.parse_errors,
        "exception_type": exception_type,
        "traceback": traceback_text[-2000:],
    }


def count_tool_stats(imports: dict[str, Any], context: Any) -> dict[str, int]:
    DatabaseNamespace = imports["DatabaseNamespace"]
    RoleType = imports["RoleType"]
    sandbox = context.get_database(
        DatabaseNamespace.SANDBOX,
        get_all_history_snapshots=True,
        drop_sandbox_message_index=False,
    )
    rows = sandbox.to_dicts()
    agent_tool_calls = [
        row
        for row in rows
        if row.get("sender") == RoleType.AGENT
        and row.get("recipient") == RoleType.EXECUTION_ENVIRONMENT
    ]
    agent_tool_responses = [
        row
        for row in rows
        if row.get("sender") == RoleType.EXECUTION_ENVIRONMENT
        and row.get("recipient") == RoleType.AGENT
    ]
    invalid = sum(1 for row in agent_tool_responses if row.get("tool_call_exception"))
    return {
        "tool_calls": len(agent_tool_calls),
        "invalid_tool_calls": invalid,
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for method in sorted({row["method"] for row in rows}):
        subset = [row for row in rows if row["method"] == method]
        summary.append(
            {
                "method": method,
                "episodes": len(subset),
                "success_rate": mean_bool(subset, "success"),
                "mean_similarity": mean(subset, "similarity"),
                "unsafe_state_changes_per_task": mean(subset, "unsafe_state_changes"),
                "invalid_tool_calls_per_task": mean(subset, "invalid_tool_calls"),
                "verifier_rejections_per_task": mean(subset, "verifier_rejections"),
                "repair_calls_per_task": mean(subset, "repair_calls"),
                "llm_calls_per_task": mean(subset, "llm_calls"),
                "tool_calls_per_task": mean(subset, "tool_calls"),
                "token_proxy_per_task": mean(subset, "token_proxy"),
                "user_llm_calls_per_task": mean(subset, "user_llm_calls"),
                "user_token_proxy_per_task": mean(subset, "user_token_proxy"),
                "parse_errors_per_task": mean(subset, "parse_errors"),
            }
        )
    return summary


def judge_kill_criteria(
    summary: list[dict[str, Any]],
    *,
    min_invalid_reduction: float,
    min_success_delta: float,
    max_cost_multiplier: float,
) -> dict[str, Any]:
    by_method = {row["method"]: row for row in summary}
    react = by_method.get("ToolSandbox ReAct")
    candidate = by_method.get("ToolSandbox RAVE")
    if react is None or candidate is None:
        return {
            "decision": (
                "INCONCLUSIVE: ToolSandbox ReAct and ToolSandbox RAVE are required. "
                "PCTU is only an ablation, not the primary method."
            ),
            "checks": {},
        }

    react_invalid = react["invalid_tool_calls_per_task"]
    candidate_invalid = candidate["invalid_tool_calls_per_task"]
    invalid_reduction = (
        0.0 if react_invalid == 0 else (react_invalid - candidate_invalid) / react_invalid
    )
    success_delta = candidate["success_rate"] - react["success_rate"]
    llm_cost_multiplier = ratio(candidate["llm_calls_per_task"], react["llm_calls_per_task"])
    token_cost_multiplier = ratio(candidate["token_proxy_per_task"], react["token_proxy_per_task"])

    checks = {
        "candidate": candidate["method"],
        "invalid_reduction": round(invalid_reduction, 4),
        "success_delta": round(success_delta, 4),
        "llm_cost_multiplier": round(llm_cost_multiplier, 4),
        "token_cost_multiplier": round(token_cost_multiplier, 4),
        "unsafe_not_worse": candidate["unsafe_state_changes_per_task"] <= react["unsafe_state_changes_per_task"],
        "invalid_pass": react_invalid > 0 and invalid_reduction >= min_invalid_reduction,
        "success_pass": success_delta >= min_success_delta,
        "cost_pass": llm_cost_multiplier <= max_cost_multiplier
        and token_cost_multiplier <= max_cost_multiplier,
    }
    if checks["invalid_pass"] and checks["success_pass"] and checks["cost_pass"] and checks["unsafe_not_worse"]:
        decision = "CONTINUE: ToolSandbox kill criteria passed."
    else:
        decision = (
            "STOP_CANDIDATE: ToolSandbox kill criteria did not pass. "
            "Do not make broad claims from this method without a stronger result."
        )
    return {"decision": decision, "checks": checks}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"# {title}\n\n")
        if not rows:
            handle.write("No rows.\n")
            return
        headers = list(rows[0].keys())
        handle.write("| " + " | ".join(headers) + " |\n")
        handle.write("| " + " | ".join("---" for _ in headers) + " |\n")
        for row in rows:
            handle.write("| " + " | ".join(str(row[h]) for h in headers) + " |\n")


def write_verdict(path: Path, verdict: dict[str, Any], summary: list[dict[str, Any]], args: argparse.Namespace) -> None:
    lines = [
        "# ToolSandbox Kill Criteria",
        "",
        f"Decision: **{verdict['decision']}**",
        "",
        "Checks:",
    ]
    for key, value in verdict.get("checks", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "Thresholds:",
            f"- min_invalid_reduction: {args.min_invalid_reduction}",
            f"- min_success_delta: {args.min_success_delta}",
            f"- max_cost_multiplier: {args.max_cost_multiplier}",
            "",
            "Summary:",
            json.dumps(summary, indent=2, ensure_ascii=False),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_metadata(
    path: Path,
    args: argparse.Namespace,
    scenario_names: list[str],
    rapidapi_fixture_enabled: bool,
) -> None:
    metadata = {
        "benchmark": "ToolSandbox public stateful tool-use benchmark",
        "model": args.model,
        "base_url": args.base_url,
        "scenario_suite": args.scenario_suite,
        "scenario_count": len(scenario_names),
        "scenarios": scenario_names,
        "methods": args.methods,
        "user_mode": args.user_mode,
        "rapidapi_fixture": args.rapidapi_fixture,
        "rapidapi_fixture_enabled": rapidapi_fixture_enabled,
        "note": "Use --user-mode local-llm for multi-turn or insufficient-information suites.",
    }
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def mean(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(statistics.fmean(float(row[key]) for row in rows), 4)


def mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1.0 if row[key] else 0.0 for row in rows) / len(rows), 4)


def ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return float("inf") if numerator else 1.0
    return numerator / denominator


if __name__ == "__main__":
    main()
