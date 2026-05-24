"""Static AppWorld instruction-coverage audit for the ICVE registry.

This script intentionally does not start an AppWorld environment, execute tools, or load
ground-truth files. It reads public task IDs and public task instructions from
``specs.json``, runs the ICVE AppWorld intent registry's compile step, and reports which
instructions compile to complete intent frames.

The resulting numbers are coverage diagnostics, not task-success or leaderboard
metrics. They are useful for auditing whether coverage is concentrated in a small
prefix or extends across held-out AppWorld task files without silently mutating state for
unsupported requests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pctu_pilot.appworld_agents import build_appworld_intent_machines  # noqa: E402
from pctu_pilot.rave_runtime import RaveRuntime  # noqa: E402


DEFAULT_SPLITS = ("test_normal", "test_challenge")


ROADMAP_BY_BUCKET = {
    "amazon_purchase_or_product_search": {
        "roadmap_family": "Amazon search-and-purchase machines",
        "required_machine_capability": (
            "Rank product candidates from public attributes, ground seller and variant "
            "constraints, verify cart/order preconditions, and execute bounded purchase "
            "or save-for-later transitions."
        ),
        "why_not_currently_covered": (
            "Current AppWorld registry covers narrow saved-list and order-state workflows, "
            "but not open product search, candidate ranking, or multi-item cart planning."
        ),
        "validation_gate": (
            "Pass an Amazon-only held-out slice using public instructions and packaged "
            "evaluator goals, with zero unsafe purchases on unsupported or ambiguous cases."
        ),
    },
    "gmail_email": {
        "roadmap_family": "Gmail thread-and-draft machines",
        "required_machine_capability": (
            "Resolve threads and recipients, summarize or filter message evidence, build "
            "draft/send frames, and enforce missing-recipient/content abstention."
        ),
        "why_not_currently_covered": (
            "Current registry does not model email-thread evidence selection, draft state, "
            "or send/reply/forward transitions."
        ),
        "validation_gate": (
            "Evaluate a Gmail-only held-out slice with thread grounding traces, no sends "
            "without grounded recipients, and explicit abstentions for underspecified mail."
        ),
    },
    "splitwise_vacation_or_expense": {
        "roadmap_family": "Splitwise expense-settlement machines",
        "required_machine_capability": (
            "Aggregate group-trip expenses, compute per-user balances, select settlement "
            "actions, and verify no duplicate or wrong-party payments."
        ),
        "why_not_currently_covered": (
            "Current machines avoid multi-party vacation accounting because it requires "
            "cross-record aggregation beyond the existing compact state transitions."
        ),
        "validation_gate": (
            "Run a vacation/expense held-out slice with independently checked balance "
            "invariants and no hidden-answer access during machine construction."
        ),
    },
    "spotify_music": {
        "roadmap_family": "Spotify search-and-library machines",
        "required_machine_capability": (
            "Ground artists, albums, tracks, and playlists under ambiguous search results, "
            "then apply library or playlist mutations with duplicate detection."
        ),
        "why_not_currently_covered": (
            "Current registry covers targeted Spotify navigation cases, but not broad "
            "music search, ranking, or playlist transformation workflows."
        ),
        "validation_gate": (
            "Pass a Spotify held-out slice with search-result grounding logs and zero "
            "duplicate playlist/library mutations."
        ),
    },
    "venmo_payment_or_request": {
        "roadmap_family": "Venmo payment/request machines",
        "required_machine_capability": (
            "Ground counterparties, distinguish payment from request intent, reason over "
            "visible funding evidence, and abstain when balance or recipient evidence is "
            "unavailable."
        ),
        "why_not_currently_covered": (
            "Current runtime handles a narrow card-repair path but intentionally avoids "
            "private balance access and broad social/payment workflows."
        ),
        "validation_gate": (
            "Evaluate Venmo tasks with zero wrong-recipient transfers and safe abstention "
            "when public evidence cannot prove a payable funding source."
        ),
    },
    "phone_message": {
        "roadmap_family": "Phone messaging machines",
        "required_machine_capability": (
            "Disambiguate contacts, ground message content, verify send targets, and "
            "separate read-only contact lookup from mutating message sends."
        ),
        "why_not_currently_covered": (
            "Current registry covers direct sends, several phone-message read/act "
            "patterns, and a narrow account-verification/reset pattern, but not "
            "recommendation-driven shopping or broad contact-message task execution."
        ),
        "validation_gate": (
            "Pass a messaging slice with explicit contact disambiguation and zero sends "
            "to ambiguous or unsupported contacts."
        ),
    },
    "todoist_task": {
        "roadmap_family": "Todoist task/project machines",
        "required_machine_capability": (
            "Ground projects, tasks, due dates, and labels; then apply create/update/close "
            "transitions with duplicate and missing-date checks."
        ),
        "why_not_currently_covered": (
            "Current AppWorld registry focuses on the observed stateful slices and does "
            "not register a full Todoist task-state model."
        ),
        "validation_gate": (
            "Run a Todoist held-out slice with task identity traces and no duplicate or "
            "wrong-project mutations."
        ),
    },
    "file_system": {
        "roadmap_family": "File-system transformation machines",
        "required_machine_capability": (
            "Ground files and directories, verify path preconditions, and perform bounded "
            "copy/move/rename/export operations."
        ),
        "why_not_currently_covered": (
            "Current file machines cover selected prefix-move/export cases, not arbitrary "
            "multi-file transformations."
        ),
        "validation_gate": (
            "Evaluate a file-operation slice with path-diff checks and no destructive "
            "operations outside grounded targets."
        ),
    },
    "simple_note": {
        "roadmap_family": "Simple Note content machines",
        "required_machine_capability": (
            "Ground notes, inspect content, and apply constrained create/update/export "
            "transitions with idempotent completion checks."
        ),
        "why_not_currently_covered": (
            "Current note coverage is limited to selected markdown export workflows."
        ),
        "validation_gate": (
            "Pass note-editing tasks with before/after content checks and no edits to "
            "ambiguous notes."
        ),
    },
    "other_or_multi_app": {
        "roadmap_family": "Cross-application intent machines",
        "required_machine_capability": (
            "Decompose requests across apps, make intermediate state explicit, and verify "
            "each mutating transition against app-local invariants."
        ),
        "why_not_currently_covered": (
            "Current registry is intentionally app-family scoped and does not synthesize "
            "open-ended cross-app plans."
        ),
        "validation_gate": (
            "Create a held-out multi-app slice with visible intermediate ledgers and "
            "per-transition invariant checks."
        ),
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit AppWorld public-instruction compile coverage for ICVE."
    )
    parser.add_argument(
        "--appworld-root",
        default=str(ROOT / "appworld_020_root"),
        help="Local AppWorld data root containing data/datasets and data/tasks.",
    )
    parser.add_argument("--splits", nargs="+", default=list(DEFAULT_SPLITS))
    parser.add_argument(
        "--output-root",
        default="results/appworld_static_coverage",
        help="Output directory root. A timestamped subdirectory is created unless --output-dir is set.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Exact output directory. Overrides --output-root timestamp behavior.",
    )
    args = parser.parse_args()

    appworld_root = Path(args.appworld_root).resolve()
    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = ROOT / output_dir
    else:
        output_dir = ROOT / args.output_root / time.strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime = RaveRuntime(build_appworld_intent_machines())
    rows: list[dict[str, Any]] = []
    for split in args.splits:
        for task_id in read_task_ids(appworld_root, split):
            instruction = read_public_instruction(appworld_root, task_id)
            rows.append(audit_one(runtime, split, task_id, instruction))

    summary = summarize(rows, runtime)
    write_csv(output_dir / "episode_metrics.csv", rows)
    write_csv(output_dir / "intent_coverage.csv", intent_rows(rows))
    write_csv(output_dir / "unsupported_bucket_coverage.csv", unsupported_bucket_rows(rows))
    write_csv(output_dir / "coverage_roadmap.csv", coverage_roadmap_rows(rows))
    write_csv(output_dir / "scenario_coverage.csv", scenario_rows(rows))
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(output_dir / "README.md", summary, rows)

    print(json.dumps(summary, indent=2))
    print(f"Wrote {output_dir.relative_to(ROOT)}")


def read_task_ids(appworld_root: Path, split: str) -> list[str]:
    path = appworld_root / "data" / "datasets" / f"{split}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Missing AppWorld split file: {path}")
    return [line.strip().split(":")[0] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_public_instruction(appworld_root: Path, task_id: str) -> str:
    specs_path = appworld_root / "data" / "tasks" / task_id / "specs.json"
    if not specs_path.exists():
        raise FileNotFoundError(f"Missing AppWorld specs file: {specs_path}")
    specs = json.loads(specs_path.read_text(encoding="utf-8"))
    instruction = specs.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError(f"Missing public instruction in {specs_path}")
    return instruction.strip()


def audit_one(
    runtime: RaveRuntime,
    split: str,
    task_id: str,
    instruction: str,
) -> dict[str, Any]:
    frame = runtime.compile_frame(
        instruction,
        instruction,
        {"execute_code": _blocked_execute_code},
    )
    scenario_id = task_id.split("_", maxsplit=1)[0]
    instruction_hash = hashlib.sha256(instruction.encode("utf-8")).hexdigest()[:16]
    if frame is None:
        return {
            "split": split,
            "task_id": task_id,
            "scenario_id": scenario_id,
            "compiled": 0,
            "dispatchable": 0,
            "abstained": 0,
            "incomplete": 0,
            "intent_type": "unsupported",
            "missing_slots": "",
            "abstain_reason": "",
            "unsupported_bucket": bucket_instruction(instruction),
            "instruction_hash": instruction_hash,
        }
    missing_slots = ",".join(frame.missing_slots)
    abstained = int(bool(frame.abstain_reason))
    incomplete = int(bool(frame.missing_slots))
    dispatchable = int(not frame.missing_slots and not frame.abstain_reason)
    return {
        "split": split,
        "task_id": task_id,
        "scenario_id": scenario_id,
        "compiled": 1,
        "dispatchable": dispatchable,
        "abstained": abstained,
        "incomplete": incomplete,
        "intent_type": frame.intent_type,
        "missing_slots": missing_slots,
        "abstain_reason": frame.abstain_reason,
        "unsupported_bucket": "",
        "instruction_hash": instruction_hash,
    }


def _blocked_execute_code(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("static coverage audit must not execute AppWorld tools")


def bucket_instruction(instruction: str) -> str:
    text = instruction.lower()
    if any(term in text for term in ("amazon", "order", "cart", "seller", "product", "purchase")):
        return "amazon_purchase_or_product_search"
    if any(term in text for term in ("vacation", "trip", "splitwise", "settle", "expense")):
        return "splitwise_vacation_or_expense"
    if any(term in text for term in ("venmo", "payment", "pay ", "request money", "withdraw")):
        return "venmo_payment_or_request"
    if any(term in text for term in ("spotify", "playlist", "song", "artist", "album")):
        return "spotify_music"
    if any(term in text for term in ("gmail", "email", "draft", "inbox", "thread")):
        return "gmail_email"
    if any(term in text for term in ("todoist", "task", "reminder", "project", "deadline")):
        return "todoist_task"
    if any(term in text for term in ("file", "folder", "directory", "csv", "download")):
        return "file_system"
    if any(term in text for term in ("note", "simple note", "markdown")):
        return "simple_note"
    if any(term in text for term in ("phone", "message", "text")):
        return "phone_message"
    return "other_or_multi_app"


def summarize(rows: list[dict[str, Any]], runtime: RaveRuntime) -> dict[str, Any]:
    by_split = {}
    for split in sorted({str(row["split"]) for row in rows}):
        split_rows = [row for row in rows if row["split"] == split]
        by_split[split] = summarize_rows(split_rows)
    return {
        "audit_type": "static_public_instruction_compile_coverage",
        "not_a_success_or_leaderboard_metric": True,
        "registered_appworld_machines": len(runtime.intent_machines),
        "total_tasks": len(rows),
        "overall": summarize_rows(rows),
        "by_split": by_split,
        "top_dispatchable_intents": Counter(
            str(row["intent_type"]) for row in rows if int(row["dispatchable"])
        ).most_common(12),
        "top_unsupported_buckets": Counter(
            str(row["unsupported_bucket"]) for row in rows if not int(row["compiled"])
        ).most_common(12),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    compiled = sum(int(row["compiled"]) for row in rows)
    dispatchable = sum(int(row["dispatchable"]) for row in rows)
    abstained = sum(int(row["abstained"]) for row in rows)
    incomplete = sum(int(row["incomplete"]) for row in rows)
    unsupported = total - compiled
    scenarios = {str(row["scenario_id"]) for row in rows}
    dispatchable_scenarios = {str(row["scenario_id"]) for row in rows if int(row["dispatchable"])}
    compiled_scenarios = {str(row["scenario_id"]) for row in rows if int(row["compiled"])}
    return {
        "tasks": total,
        "compiled": compiled,
        "dispatchable": dispatchable,
        "abstained": abstained,
        "incomplete": incomplete,
        "unsupported": unsupported,
        "compiled_rate": round(compiled / total, 4) if total else 0.0,
        "dispatchable_rate": round(dispatchable / total, 4) if total else 0.0,
        "unsupported_rate": round(unsupported / total, 4) if total else 0.0,
        "scenarios": len(scenarios),
        "compiled_scenarios": len(compiled_scenarios),
        "dispatchable_scenarios": len(dispatchable_scenarios),
        "dispatchable_scenario_rate": round(len(dispatchable_scenarios) / len(scenarios), 4)
        if scenarios
        else 0.0,
    }


def intent_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if int(row["compiled"]):
            grouped[(str(row["split"]), str(row["intent_type"]))].append(row)
    output = []
    for (split, intent_type), subset in sorted(grouped.items()):
        output.append(
            {
                "split": split,
                "intent_type": intent_type,
                "compiled": len(subset),
                "dispatchable": sum(int(row["dispatchable"]) for row in subset),
                "abstained": sum(int(row["abstained"]) for row in subset),
                "incomplete": sum(int(row["incomplete"]) for row in subset),
                "scenarios": len({row["scenario_id"] for row in subset}),
            }
        )
    return sorted(output, key=lambda row: (row["split"], -row["dispatchable"], row["intent_type"]))


def unsupported_bucket_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not int(row["compiled"]):
            grouped[(str(row["split"]), str(row["unsupported_bucket"]))].append(row)
    output = []
    for (split, bucket), subset in sorted(grouped.items()):
        output.append(
            {
                "split": split,
                "unsupported_bucket": bucket,
                "tasks": len(subset),
                "scenarios": len({row["scenario_id"] for row in subset}),
            }
        )
    return sorted(output, key=lambda row: (row["split"], -row["tasks"], row["unsupported_bucket"]))


def coverage_roadmap_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for bucket_row in unsupported_bucket_rows(rows):
        bucket = str(bucket_row["unsupported_bucket"])
        roadmap = ROADMAP_BY_BUCKET.get(bucket, ROADMAP_BY_BUCKET["other_or_multi_app"])
        output.append(
            {
                "split": bucket_row["split"],
                "unsupported_bucket": bucket,
                "tasks": bucket_row["tasks"],
                "scenarios": bucket_row["scenarios"],
                "roadmap_family": roadmap["roadmap_family"],
                "required_machine_capability": roadmap["required_machine_capability"],
                "why_not_currently_covered": roadmap["why_not_currently_covered"],
                "validation_gate": roadmap["validation_gate"],
            }
        )
    return output


def scenario_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["split"]), str(row["scenario_id"]))].append(row)
    output = []
    for (split, scenario_id), subset in sorted(grouped.items()):
        dispatchable = sum(int(row["dispatchable"]) for row in subset)
        compiled = sum(int(row["compiled"]) for row in subset)
        intents = sorted({str(row["intent_type"]) for row in subset if int(row["compiled"])})
        buckets = sorted({str(row["unsupported_bucket"]) for row in subset if not int(row["compiled"])})
        output.append(
            {
                "split": split,
                "scenario_id": scenario_id,
                "tasks": len(subset),
                "compiled": compiled,
                "dispatchable": dispatchable,
                "compiled_rate": round(compiled / len(subset), 4),
                "dispatchable_rate": round(dispatchable / len(subset), 4),
                "compiled_intents": ",".join(intents),
                "unsupported_buckets": ",".join(buckets),
            }
        )
    return sorted(output, key=lambda row: (row["split"], -row["dispatchable_rate"], row["scenario_id"]))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    overall = summary["overall"]
    lines = [
        "# AppWorld Static Instruction-Coverage Audit",
        "",
        "This audit reads public AppWorld task IDs and public `specs.json` instructions,",
        "then runs only the ICVE registry compile step. It does not start AppWorld, execute",
        "tools, inspect databases, or load ground-truth files. The numbers below are",
        "compile/coverage diagnostics, not task-success or leaderboard metrics.",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| registered_appworld_machines | {summary['registered_appworld_machines']} |",
        f"| total_tasks | {overall['tasks']} |",
        f"| compiled | {overall['compiled']} |",
        f"| dispatchable | {overall['dispatchable']} |",
        f"| unsupported | {overall['unsupported']} |",
        f"| compiled_rate | {overall['compiled_rate']:.4f} |",
        f"| dispatchable_rate | {overall['dispatchable_rate']:.4f} |",
        f"| dispatchable_scenarios | {overall['dispatchable_scenarios']} / {overall['scenarios']} |",
        "",
        "## By Split",
        "",
        "| split | tasks | compiled | dispatchable | unsupported | dispatchable rate | dispatchable scenarios |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split, split_summary in summary["by_split"].items():
        lines.append(
            f"| {split} | {split_summary['tasks']} | {split_summary['compiled']} | "
            f"{split_summary['dispatchable']} | {split_summary['unsupported']} | "
            f"{split_summary['dispatchable_rate']:.4f} | "
            f"{split_summary['dispatchable_scenarios']} / {split_summary['scenarios']} |"
        )

    lines.extend(
        [
            "",
            "## Top Dispatchable Intents",
            "",
            "| intent_type | tasks |",
            "| --- | ---: |",
        ]
    )
    for intent_type, count in summary["top_dispatchable_intents"]:
        lines.append(f"| {intent_type} | {count} |")

    lines.extend(
        [
            "",
            "## Top Unsupported Buckets",
            "",
            "| bucket | tasks |",
            "| --- | ---: |",
        ]
    )
    for bucket, count in summary["top_unsupported_buckets"]:
        lines.append(f"| {bucket} | {count} |")

    roadmap_rows = coverage_roadmap_rows(rows)
    if roadmap_rows:
        lines.extend(
            [
                "",
                "## Coverage Roadmap",
                "",
                "The roadmap is derived from unsupported public-instruction buckets. It is",
                "not a solved-coverage result; it records what new machine capabilities and",
                "validation gates would be required before claiming support for each bucket.",
                "Full rows are in `coverage_roadmap.csv`.",
                "",
                "| split | bucket | tasks | scenarios | roadmap family |",
                "| --- | --- | ---: | ---: | --- |",
            ]
        )
        for row in roadmap_rows:
            lines.append(
                f"| {row['split']} | {row['unsupported_bucket']} | {row['tasks']} | "
                f"{row['scenarios']} | {row['roadmap_family']} |"
            )

    full_coverage_scenarios = [
        row
        for row in scenario_rows(rows)
        if int(row["tasks"]) == int(row["dispatchable"])
    ]
    partial_coverage_scenarios = [
        row
        for row in scenario_rows(rows)
        if int(row["dispatchable"]) and int(row["tasks"]) != int(row["dispatchable"])
    ]
    lines.extend(
        [
            "",
            "## Scenario Coverage",
            "",
            f"- Fully dispatchable scenarios: {len(full_coverage_scenarios)}",
            f"- Partially dispatchable scenarios: {len(partial_coverage_scenarios)}",
            "- Full per-scenario rows are in `scenario_coverage.csv`.",
            "",
            "Interpretation: a dispatchable compile means the current registry recognized the",
            "instruction and produced a complete typed frame. Unsupported rows are explicit",
            "coverage gaps that should remain no-action outcomes unless a new machine is",
            "added and validated.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
