from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pctu_pilot.agents import (  # noqa: E402
    JsonRepairAgent,
    ProofCarryingAgent,
    ReactAgent,
    ReflexionRetryAgent,
    RiskAdaptiveVerifiedAgent,
    StateLedgerAgent,
)
from pctu_pilot.ministore import MiniStoreEnv, make_tasks  # noqa: E402


def summarize(rows: list[dict]) -> list[dict]:
    methods = sorted({row["method"] for row in rows})
    summary: list[dict] = []
    for method in methods:
        subset = [row for row in rows if row["method"] == method]
        rejected = [row for row in subset if row["verifier_rejections"] > 0]
        summary.append(
            {
                "method": method,
                "episodes": len(subset),
                "task_success_rate": avg(subset, "success"),
                "goal_achieved_rate": avg(subset, "goal_achieved"),
                "invalid_tool_calls_per_task": mean(subset, "invalid_tool_calls"),
                "unsafe_changes_per_task": mean(subset, "unsafe_changes"),
                "collateral_changes_per_task": mean(subset, "collateral_changes"),
                "verifier_rejections_per_task": mean(subset, "verifier_rejections"),
                "recovery_after_rejection_rate": avg(rejected, "success") if rejected else "",
                "llm_calls_per_task": mean(subset, "llm_calls"),
                "tool_calls_per_task": mean(subset, "tool_calls"),
                "token_proxy_per_task": mean(subset, "token_proxy"),
            }
        )
    return summary


def summarize_by_category(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for method in sorted({row["method"] for row in rows}):
        for category in sorted({row["category"] for row in rows}):
            subset = [
                row for row in rows if row["method"] == method and row["category"] == category
            ]
            if not subset:
                continue
            out.append(
                {
                    "method": method,
                    "category": category,
                    "episodes": len(subset),
                    "task_success_rate": avg(subset, "success"),
                    "invalid_tool_calls_per_task": mean(subset, "invalid_tool_calls"),
                    "unsafe_changes_per_task": mean(subset, "unsafe_changes"),
                }
            )
    return out


def error_taxonomy(rows: list[dict]) -> list[dict]:
    keys = [
        "missing_schema_errors",
        "unsupported_argument_errors",
        "precondition_errors",
        "postcondition_errors",
        "collateral_changes",
    ]
    out: list[dict] = []
    for method in sorted({row["method"] for row in rows}):
        subset = [row for row in rows if row["method"] == method]
        record = {"method": method, "episodes": len(subset)}
        for key in keys:
            record[f"{key}_per_task"] = mean(subset, key)
        out.append(record)
    return out


def avg(rows: list[dict], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1.0 if row[key] else 0.0 for row in rows) / len(rows), 4)


def mean(rows: list[dict], key: str) -> float:
    if not rows:
        return 0.0
    return round(statistics.fmean(float(row[key]) for row in rows), 4)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_table(path: Path, rows: list[dict], title: str) -> None:
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


def write_metadata(path: Path, rows: list[dict], task_count: int, seed: int) -> None:
    metadata = {
        "benchmark": "MiniStore RAVE synthetic stateful tool-use pilot",
        "seed": seed,
        "tasks": task_count,
        "methods": sorted({row["method"] for row in rows}),
        "note": (
            "This is a controlled pilot simulator for RAVE method debugging. "
            "It is not a substitute for ToolSandbox, AppWorld, or another public benchmark."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> None:
    seed = 20260427
    tasks = make_tasks(n_per_category=125, seed=seed)
    agents = [
        ReactAgent(),
        JsonRepairAgent(),
        ReflexionRetryAgent(),
        StateLedgerAgent(),
        ProofCarryingAgent(),
        RiskAdaptiveVerifiedAgent(),
    ]

    rows: list[dict] = []
    for agent in agents:
        for task in tasks:
            env = MiniStoreEnv(task)
            stats = agent.run(env)
            rows.append(stats.to_row())

    results_dir = ROOT / "results"
    summary = summarize(rows)
    by_category = summarize_by_category(rows)
    taxonomy = error_taxonomy(rows)

    write_csv(results_dir / "episode_metrics.csv", rows)
    write_csv(results_dir / "pilot_summary.csv", summary)
    write_csv(results_dir / "category_summary.csv", by_category)
    write_csv(results_dir / "error_taxonomy.csv", taxonomy)
    write_markdown_table(results_dir / "pilot_summary.md", summary, "Pilot Summary")
    write_markdown_table(
        results_dir / "category_summary.md", by_category, "Pilot Summary by Category"
    )
    write_markdown_table(
        results_dir / "error_taxonomy.md", taxonomy, "Pilot Error Taxonomy"
    )
    write_metadata(results_dir / "metadata.json", rows, task_count=len(tasks), seed=seed)

    print(f"Wrote {len(rows)} episode rows for {len(agents)} methods over {len(tasks)} tasks.")
    print(results_dir / "pilot_summary.md")


if __name__ == "__main__":
    main()
