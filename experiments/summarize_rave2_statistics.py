from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SuiteSpec:
    label: str
    summary_path: Path
    methods: tuple[str, ...]


SUITES: tuple[SuiteSpec, ...] = (
    SuiteSpec(
        "3B single-turn",
        ROOT
        / "results/toolsandbox_qwen25_3b_rave2_single_turn_compare_fixed/20260501_144845/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no RAVE-2 DSL",
            "ToolSandbox RAVE - no abstention verifier",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "3B insufficient-information",
        ROOT
        / "results/toolsandbox_qwen25_3b_rave2_insufficient_compare_fixed2/20260501_153424/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no abstention verifier",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "0.5B single-turn",
        ROOT
        / "results/toolsandbox_qwen25_05b_rave2_single_turn_compare_fixed/20260501_160536/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no RAVE-2 DSL",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "0.5B insufficient-information",
        ROOT / "results/toolsandbox_qwen25_05b_rave2_insufficient_compare/20260501_162021/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no abstention verifier",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "7B-4bit single-turn",
        ROOT
        / "results/toolsandbox_qwen25_7b_4bit_rave2_single_turn_compare_contact_name_patch/20260504_001328/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no RAVE-2 DSL",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "7B-4bit insufficient-information",
        ROOT
        / "results/toolsandbox_qwen25_7b_4bit_rave2_insufficient_compare_contact_name_patch/20260504_002013/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no abstention verifier",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "Phi-3-mini core10",
        ROOT / "results/toolsandbox_phi3_mini_rave2_core10_compare/20260504_023509/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "Phi-3-mini insufficient10",
        ROOT
        / "results/toolsandbox_phi3_mini_rave2_insufficient10_compare/20260504_023708/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no abstention verifier",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "DeepSeek single-turn",
        ROOT
        / "results/frontier_toolsandbox_replication_deepseek/deepseek-chat_single_turn_patch_final/20260504_114435/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no RAVE-2 DSL",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "DeepSeek insufficient-information",
        ROOT
        / "results/frontier_toolsandbox_replication_deepseek/deepseek-chat_insufficient/20260504_041631/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no abstention verifier",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "DeepSeek-reasoner single-turn",
        ROOT
        / "results/frontier_toolsandbox_replication_deepseek_reasoner/deepseek-reasoner_single_turn/20260504_122044/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no RAVE-2 DSL",
            "ToolSandbox ReAct",
        ),
    ),
    SuiteSpec(
        "DeepSeek-reasoner insufficient-information",
        ROOT
        / "results/frontier_toolsandbox_replication_deepseek_reasoner/deepseek-reasoner_insufficient/20260504_124227/summary.csv",
        (
            "ToolSandbox RAVE",
            "ToolSandbox RAVE - no abstention verifier",
            "ToolSandbox ReAct",
        ),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate RAVE-2 Wilson intervals and safety/cost summaries from result CSVs."
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "results/statistical_intervals_20260504.md"),
        help="Markdown output path.",
    )
    args = parser.parse_args()

    suites = [(spec, read_summary(spec.summary_path)) for spec in SUITES]
    output = render_markdown(suites)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    print(f"Wrote {output_path}")


def read_summary(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_method = {row["method"]: row for row in rows}
    return by_method


def render_markdown(suites: Iterable[tuple[SuiteSpec, dict[str, dict[str, str]]]]) -> str:
    lines = [
        "# Statistical Intervals, 2026-05-04",
        "",
        "Generated by `experiments/summarize_rave2_statistics.py` from recorded",
        "`summary.csv` files. Intervals are Wilson 95% confidence intervals for success",
        "rates over fixed public ToolSandbox slices. Invalid, unsafe, repair, LLM-call,",
        "and token columns are per-episode means from the same summaries.",
        "",
        "## Success Intervals",
        "",
        "| suite | method | n | success | 95% CI |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    materialized = list(suites)
    for spec, rows in materialized:
        for method in spec.methods:
            row = require_method(spec, rows, method)
            n = as_int(row["episodes"])
            success = as_float(row["success_rate"])
            successes = round(success * n)
            lo, hi = wilson_interval(successes, n)
            lines.append(
                f"| {spec.label} | {method} | {n} | {success:.4f} | [{lo:.4f}, {hi:.4f}] |"
            )

    lines.extend(
        [
            "",
            "## Safety and Cost Means",
            "",
            "| suite | method | invalid | unsafe | repair | LLM calls | token proxy |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for spec, rows in materialized:
        for method in spec.methods:
            row = require_method(spec, rows, method)
            lines.append(
                "| "
                + " | ".join(
                    [
                        spec.label,
                        method,
                        fmt(row["invalid_tool_calls_per_task"]),
                        fmt(row["unsafe_state_changes_per_task"]),
                        fmt(row["repair_calls_per_task"]),
                        fmt(row["llm_calls_per_task"]),
                        fmt(row["token_proxy_per_task"]),
                    ]
                )
                + " |"
            )

    lines.append("")
    return "\n".join(lines)


def require_method(
    spec: SuiteSpec,
    rows: dict[str, dict[str, str]],
    method: str,
) -> dict[str, str]:
    try:
        return rows[method]
    except KeyError as exc:
        available = ", ".join(sorted(rows))
        raise KeyError(f"{method!r} missing from {spec.summary_path}; available: {available}") from exc


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2.0 * n)) / denom
    half = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)


def as_float(value: str) -> float:
    return float(value)


def as_int(value: str) -> int:
    return int(float(value))


def fmt(value: str) -> str:
    return f"{float(value):.4f}"


if __name__ == "__main__":
    main()
