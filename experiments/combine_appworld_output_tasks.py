from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine AppWorld experiments/outputs task directories by task_id."
    )
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dedupe-key", default="task_id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    inputs = [ROOT / path for path in args.inputs]
    output_dir = ROOT / args.output_dir
    tasks_by_id = collect_tasks(inputs)

    if output_dir.exists() and not args.dry_run:
        raise FileExistsError(f"Output directory already exists: {output_dir}")

    if not args.dry_run:
        (output_dir / "tasks").mkdir(parents=True)
        for task_id, task_path in sorted(tasks_by_id.items()):
            shutil.copytree(task_path, output_dir / "tasks" / task_id)
        metadata = {
            "combined_from": args.inputs,
            "dedupe_key": args.dedupe_key,
            "task_ids": sorted(tasks_by_id),
            "note": "Combined from AppWorld experiments/outputs task directories.",
        }
        (output_dir / "combined_output_tasks.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

    print(f"unique_tasks {len(tasks_by_id)}")
    print(f"output_dir {output_dir}")


def collect_tasks(inputs: list[Path]) -> dict[str, Path]:
    tasks_by_id: dict[str, Path] = {}
    for input_dir in inputs:
        tasks_dir = input_dir / "tasks"
        if not tasks_dir.is_dir():
            raise FileNotFoundError(f"Missing tasks directory: {tasks_dir}")
        for task_path in sorted(path for path in tasks_dir.iterdir() if path.is_dir()):
            task_id = task_path.name
            if task_id in tasks_by_id:
                first = tasks_by_id[task_id]
                raise ValueError(f"Duplicate task_id={task_id}: {first} and {task_path}")
            tasks_by_id[task_id] = task_path
    return tasks_by_id


if __name__ == "__main__":
    main()
