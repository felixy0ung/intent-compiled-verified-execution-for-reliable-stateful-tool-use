from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import warnings
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from appworld.environment import AppWorld  # noqa: E402
from appworld.task import Task  # noqa: E402
from pctu_pilot.appworld_agents import (  # noqa: E402
    AppWorldLLMCodeAgent,
    AppWorldLLMCodeRepairAgent,
    AppWorldLLMIntentCodeAgent,
    AppWorldLLMIntentAgent,
    AppWorldLLMReactCodeAgent,
    AppWorldRaveAgent,
)
from pctu_pilot.llm_client import OpenAICompatibleClient  # noqa: E402


DEFAULT_TASK_IDS = [
    "0d8a4ee_1",
    "0d8a4ee_2",
    "0d8a4ee_3",
    "13547f5_1",
    "13547f5_2",
    "13547f5_3",
    "37a8675_1",
    "37a8675_2",
    "37a8675_3",
    "024c982_1",
    "024c982_2",
    "024c982_3",
    "4fab96f_1",
    "4fab96f_2",
    "4fab96f_3",
    "6ea6792_1",
    "6ea6792_2",
    "6ea6792_3",
    "ff58e36_1",
    "ff58e36_2",
    "ff58e36_3",
    "5e27cd7_1",
    "5e27cd7_2",
    "5e27cd7_3",
    "09ac073_1",
    "09ac073_2",
    "09ac073_3",
    "771d8fc_1",
    "771d8fc_2",
    "771d8fc_3",
    "cf6abd2_1",
    "cf6abd2_2",
    "cf6abd2_3",
    "07b42fd_1",
    "07b42fd_2",
    "07b42fd_3",
    "aa8502b_1",
    "aa8502b_2",
    "aa8502b_3",
    "6171bbc_1",
    "6171bbc_2",
    "6171bbc_3",
    "f3f60f0_1",
    "f3f60f0_2",
    "f3f60f0_3",
    "3ab5b8b_1",
    "3ab5b8b_2",
    "3ab5b8b_3",
    "692c77d_1",
    "692c77d_2",
    "692c77d_3",
    "31dc501_1",
    "31dc501_2",
    "31dc501_3",
    "07bb666_1",
    "07bb666_2",
    "07bb666_3",
    "396c5a2_1",
    "396c5a2_2",
    "396c5a2_3",
    "57c3486_1",
    "57c3486_2",
    "57c3486_3",
    "652485c_1",
    "652485c_2",
    "652485c_3",
    "d4e9306_1",
    "d4e9306_2",
    "d4e9306_3",
    "b7a9ee9_1",
    "b7a9ee9_2",
    "b7a9ee9_3",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a small public AppWorld stateful RAVE compiler/runtime slice."
    )
    parser.add_argument("--appworld-root", default=str(ROOT))
    parser.add_argument("--output-root", default="results/appworld_rave_slice")
    parser.add_argument("--experiment-name", default="")
    parser.add_argument("--task-ids", nargs="+", default=DEFAULT_TASK_IDS)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument(
        "--agent",
        choices=(
            "deterministic",
            "llm-intent",
            "llm-code",
            "llm-code-repair",
            "llm-intent-code",
            "llm-react-code",
        ),
        default="deterministic",
        help=(
            "Use regex compilers, a real LLM for typed intent/slot extraction, "
            "a direct LLM code baseline, a code baseline with repair retries, "
            "a typed-intent-only code ablation, or a multi-step code-observation baseline."
        ),
    )
    parser.add_argument("--base-url", default=os.environ.get("FRONTIER_BASE_URL", ""))
    parser.add_argument("--model", default=os.environ.get("FRONTIER_MODEL", ""))
    parser.add_argument("--api-key", default=os.environ.get("FRONTIER_API_KEY", ""))
    parser.add_argument("--client-timeout-seconds", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--repair-attempts", type=int, default=3)
    parser.add_argument(
        "--resume-output-dir",
        default="",
        help="Reuse an existing timestamped output directory and skip task_ids already recorded there.",
    )
    parser.add_argument(
        "--flush-each-task",
        action="store_true",
        help="Write episode_metrics.csv, summary.csv, metadata.json, and README.md after every task.",
    )
    args = parser.parse_args()

    os.environ["APPWORLD_ROOT"] = args.appworld_root
    warnings.filterwarnings("ignore", category=Warning, module="jwt")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.resume_output_dir) if args.resume_output_dir else ROOT / args.output_root / timestamp
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    method_by_agent = {
        "deterministic": "rave_appworld_slice",
        "llm-intent": "rave_appworld_llm_intent_slice",
        "llm-code": "appworld_llm_direct_code_slice",
        "llm-code-repair": "appworld_llm_code_repair_slice",
        "llm-intent-code": "appworld_llm_intent_code_slice",
        "llm-react-code": "appworld_llm_react_code_slice",
    }
    method = method_by_agent[args.agent]
    experiment_name = args.experiment_name or f"{method}_{timestamp}"

    rows: list[dict[str, Any]] = read_existing_rows(output_dir / "episode_metrics.csv")
    completed_task_ids = {str(row["task_id"]) for row in rows}
    if completed_task_ids:
        print(f"Resuming {output_dir}; skipping {len(completed_task_ids)} completed tasks.")

    metadata = {
        "benchmark": "AppWorld public dev/train stateful slice",
        "method": method,
        "agent": args.agent,
        "model": args.model if args.agent != "deterministic" else "",
        "experiment_name": experiment_name,
        "task_ids": args.task_ids,
        "appworld_root": args.appworld_root,
        "note": (
            "This is a targeted public AppWorld slice, not a full AppWorld "
            "leaderboard run. It does not use ground-truth solution code or "
            "ground-truth public_data to construct actions."
        ),
    }
    agent = build_agent(args)
    for task_id in args.task_ids:
        if task_id in completed_task_ids:
            continue
        row = run_one_task(
            task_id=task_id,
            agent=agent,
            method=method,
            agent_name=args.agent,
            model=args.model if args.agent != "deterministic" else "",
            experiment_name=experiment_name,
            timeout_seconds=args.timeout_seconds,
        )
        rows.append(row)
        completed_task_ids.add(task_id)
        print(
            task_id,
            rows[-1]["intent_type"],
            "success=" + str(rows[-1]["success"]),
            "invalid=" + str(rows[-1]["invalid_tool_calls"]),
            "unsafe=" + str(rows[-1]["unsafe_state_changes"]),
            "llm_calls=" + str(rows[-1]["llm_calls"]),
        )
        if args.flush_each_task:
            write_run_outputs(output_dir, rows, method, metadata)

    write_run_outputs(output_dir, rows, method, metadata)
    print(f"Wrote AppWorld RAVE slice results to {output_dir}")


def build_agent(
    args: argparse.Namespace,
) -> AppWorldRaveAgent | AppWorldLLMIntentAgent | AppWorldLLMCodeAgent | AppWorldLLMCodeRepairAgent | AppWorldLLMIntentCodeAgent | AppWorldLLMReactCodeAgent:
    if args.agent == "deterministic":
        return AppWorldRaveAgent()
    if not args.base_url:
        raise SystemExit("--base-url or FRONTIER_BASE_URL is required for LLM AppWorld agents")
    if not args.model:
        raise SystemExit("--model or FRONTIER_MODEL is required for LLM AppWorld agents")
    if not args.api_key:
        raise SystemExit("--api-key or FRONTIER_API_KEY is required for LLM AppWorld agents")
    client = OpenAICompatibleClient(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        timeout_s=args.client_timeout_seconds,
    )
    if args.agent == "llm-intent":
        return AppWorldLLMIntentAgent(
            client,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
    if args.agent == "llm-code":
        max_tokens = 1400 if args.max_tokens == 512 else args.max_tokens
        return AppWorldLLMCodeAgent(
            client,
            temperature=args.temperature,
            max_tokens=max_tokens,
        )
    if args.agent == "llm-intent-code":
        max_tokens = 1400 if args.max_tokens == 512 else args.max_tokens
        return AppWorldLLMIntentCodeAgent(
            client,
            temperature=args.temperature,
            max_tokens=max_tokens,
        )
    if args.agent == "llm-react-code":
        max_tokens = 1400 if args.max_tokens == 512 else args.max_tokens
        return AppWorldLLMReactCodeAgent(
            client,
            temperature=args.temperature,
            max_tokens=max_tokens,
            max_steps=args.repair_attempts,
        )
    max_tokens = 1400 if args.max_tokens == 512 else args.max_tokens
    return AppWorldLLMCodeRepairAgent(
        client,
        temperature=args.temperature,
        max_tokens=max_tokens,
        max_attempts=args.repair_attempts,
    )


def run_one_task(
    *,
    task_id: str,
    agent: AppWorldRaveAgent | AppWorldLLMIntentAgent | AppWorldLLMCodeAgent | AppWorldLLMCodeRepairAgent | AppWorldLLMIntentCodeAgent | AppWorldLLMReactCodeAgent,
    method: str,
    agent_name: str,
    model: str,
    experiment_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    # Load only the public task instruction. Evaluation is performed later through
    # AppWorld's tracker; the agent must never receive or load oracle data.
    task = Task.load(task_id, load_ground_truth=False)
    instruction = task.instruction
    difficulty = ""
    task.close()

    with AppWorld(
        task_id=task_id,
        experiment_name=experiment_name,
        add_login_shortcut=True,
        allow_datetime_change=True,
        raise_on_failure=False,
        timeout_seconds=timeout_seconds,
    ) as world:
        result = agent.run_instruction(instruction, world.execute)
        tracker = world.evaluate(suppress_errors=True)
        tracker_dict = tracker.to_dict(stats_only=False)
        failures = tracker_dict.get("failures", [])
        no_op_pass_failures = [
            failure for failure in failures if failure.get("label") == "no_op_pass"
        ]
        output_failed = result.output.startswith("Execution failed")
        unsupported = not result.supported
        structured_output = parse_last_json_object(result.output)
        failed_api_attempts = int(structured_output.get("failed_api_attempts", 0))
        api_calls = count_api_calls(world.output_logs_directory)
        unsafe_state_changes = 0 if unsupported else len(no_op_pass_failures)
        world.save_logs()

    return {
        "method": method,
        "agent": agent_name,
        "model": model,
        "task_id": task_id,
        "difficulty": difficulty,
        "intent_type": result.intent_type,
        "supported": int(result.supported),
        "success": int(bool(tracker.success)),
        "pass_count": tracker.pass_count,
        "fail_count": tracker.fail_count,
        "num_tests": tracker.num_tests,
        "invalid_tool_calls": int(output_failed or unsupported) + failed_api_attempts,
        "failed_api_attempts": failed_api_attempts,
        "unsafe_state_changes": unsafe_state_changes,
        "api_calls": api_calls,
        "code_exec_calls": result.code_exec_calls if result.code_exec_calls else (1 if result.supported else 0),
        "llm_calls": result.llm_calls,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "token_proxy": (
            result.prompt_tokens + result.completion_tokens
            if result.prompt_tokens or result.completion_tokens
            else len(instruction.split()) + len(result.code.split())
        ),
        "reason": result.reason,
        "execution_failed": int(output_failed),
        "parse_error": result.parse_error,
        "raw_model_output_preview": one_line(result.raw_model_output)[:500],
        "output_preview": one_line(result.output)[:300],
        "failed_requirements": " | ".join(
            one_line(failure.get("requirement", "")) for failure in failures
        )[:500],
    }


def count_api_calls(logs_directory: str) -> int:
    path = Path(logs_directory) / "api_calls.jsonl"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def parse_last_json_object(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def summarize(rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    return {
        "method": method,
        "episodes": len(rows),
        "success_rate": mean_bool(rows, "success"),
        "supported_rate": mean_bool(rows, "supported"),
        "invalid_tool_calls_per_task": mean(rows, "invalid_tool_calls"),
        "unsafe_state_changes_per_task": mean(rows, "unsafe_state_changes"),
        "api_calls_per_task": mean(rows, "api_calls"),
        "code_exec_calls_per_task": mean(rows, "code_exec_calls"),
        "llm_calls_per_task": mean(rows, "llm_calls"),
        "prompt_tokens_per_task": mean(rows, "prompt_tokens"),
        "completion_tokens_per_task": mean(rows, "completion_tokens"),
        "token_proxy_per_task": mean(rows, "token_proxy"),
    }


def mean_bool(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row[key]) / len(rows), 4)


def mean(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(statistics.fmean(float(row[key]) for row in rows), 4)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_run_outputs(
    output_dir: Path,
    rows: list[dict[str, Any]],
    method: str,
    metadata: dict[str, Any],
) -> None:
    if not rows:
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        return
    summary = summarize(rows, method)
    write_csv(output_dir / "episode_metrics.csv", rows)
    write_csv(output_dir / "summary.csv", [summary])
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    write_markdown(output_dir / "README.md", summary, rows)


def write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    method = str(summary.get("method", ""))
    if method == "appworld_llm_direct_code_slice":
        description = (
            "This run evaluates a direct LLM AppWorld code baseline on the targeted "
            "public stateful slice."
        )
    elif method == "appworld_llm_code_repair_slice":
        description = (
            "This run evaluates a multi-attempt LLM AppWorld code-repair baseline on "
            "the targeted public stateful slice."
        )
    elif method == "appworld_llm_intent_code_slice":
        description = (
            "This run evaluates a typed-intent-only LLM AppWorld code ablation on the "
            "targeted public stateful slice."
        )
    elif method == "appworld_llm_react_code_slice":
        description = (
            "This run evaluates a multi-step LLM AppWorld code-observation baseline on "
            "the targeted public stateful slice."
        )
    elif method == "rave_appworld_llm_intent_slice":
        description = (
            "This run evaluates real-LLM typed intent extraction with the verified "
            "RAVE AppWorld runtime on the targeted public stateful slice."
        )
    else:
        description = (
            "This run evaluates a targeted public AppWorld stateful slice with typed "
            "RAVE intent compilers."
        )
    lines = [
        "# AppWorld RAVE Slice",
        "",
        description,
        "It is not a full AppWorld leaderboard run.",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key, value in summary.items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Episodes",
            "",
            "| task_id | intent_type | success | invalid | unsafe | llm_calls |",
        ]
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(row[key])
                for key in [
                    "task_id",
                    "intent_type",
                    "success",
                    "invalid_tool_calls",
                    "unsafe_state_changes",
                    "llm_calls",
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def one_line(text: str) -> str:
    return " ".join(str(text).split())


if __name__ == "__main__":
    main()
