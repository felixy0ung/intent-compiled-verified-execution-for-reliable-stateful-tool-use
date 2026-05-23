from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from experiments.run_appworld_rave_slice import summarize, write_csv, write_markdown  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine AppWorld episode CSV shards.")
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--experiment-name", required=True)
    parser.add_argument("--dedupe-key", default="task_id")
    args = parser.parse_args()

    rows = read_rows([ROOT / path for path in args.inputs], args.dedupe_key)
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = summarize(rows, args.method)
    write_csv(output_dir / "episode_metrics.csv", rows)
    write_csv(output_dir / "summary.csv", [summary])
    metadata: dict[str, Any] = {
        "benchmark": "AppWorld public dev/train stateful slice",
        "method": args.method,
        "experiment_name": args.experiment_name,
        "combined_from": args.inputs,
        "dedupe_key": args.dedupe_key,
        "task_ids": [row.get("task_id", "") for row in rows],
        "note": "Combined from incrementally flushed AppWorld shard outputs.",
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    write_markdown(output_dir / "README.md", summary, rows)
    print(f"Wrote combined AppWorld results to {output_dir}")


def read_rows(paths: list[Path], dedupe_key: str) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = str(row.get(dedupe_key, ""))
                if not key:
                    raise ValueError(f"Missing {dedupe_key} in {path}")
                if key in rows_by_key:
                    raise ValueError(f"Duplicate {dedupe_key}={key} across input shards")
                rows_by_key[key] = coerce_row(row)
    return list(rows_by_key.values())


def coerce_row(row: dict[str, str]) -> dict[str, Any]:
    int_keys = {
        "supported",
        "success",
        "pass_count",
        "fail_count",
        "num_tests",
        "invalid_tool_calls",
        "failed_api_attempts",
        "unsafe_state_changes",
        "api_calls",
        "code_exec_calls",
        "llm_calls",
        "prompt_tokens",
        "completion_tokens",
        "token_proxy",
        "execution_failed",
    }
    coerced: dict[str, Any] = dict(row)
    for key in int_keys:
        if key in coerced and coerced[key] != "":
            coerced[key] = int(float(str(coerced[key])))
    return coerced


if __name__ == "__main__":
    main()
