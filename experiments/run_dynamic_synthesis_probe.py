from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOL_SANDBOX = ROOT / "third_party" / "ToolSandbox-main"
for path in (ROOT, SRC, TOOL_SANDBOX):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.run_toolsandbox_kill_criteria import import_toolsandbox_runtime, run_one  # noqa: E402
from pctu_pilot.llm_client import OpenAICompatibleClient  # noqa: E402


DEFAULT_SCENARIOS = [
    "cellular_off",
    "wifi_off",
    "turn_on_wifi_low_battery_mode",
    "turn_on_cellular_low_battery_mode",
    "turn_on_location_low_battery_mode",
]


class StubClient(OpenAICompatibleClient):
    def __init__(self) -> None:
        pass

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dynamic synthesis probe should not call the LLM")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the ICVE dynamic-machine-synthesis probe from an empty static "
            "IntentMachine registry on regular ToolSandbox setting scenarios."
        )
    )
    parser.add_argument("--scenarios", nargs="*", default=DEFAULT_SCENARIOS)
    parser.add_argument("--max-messages", type=int, default=20)
    parser.add_argument("--output-dir", default="results/dynamic_synthesis_probe")
    args = parser.parse_args()

    imports = import_toolsandbox_runtime()
    scenarios = imports["resolve_scenarios"](
        desired_scenario_names=args.scenarios,
        preferred_tool_backend=imports["ToolBackend"].DEFAULT,
    )

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for name, scenario in scenarios.items():
        row = run_one(
            imports=imports,
            client=StubClient(),
            method="rave_dynamic_synthesis",
            scenario_name=name,
            scenario=scenario,
            output_dir=output_dir,
            temperature=0.0,
            max_tokens=1,
            max_messages=args.max_messages,
            user_mode="passive",
            user_max_tokens=1,
        )
        rows.append(row)
        print(
            f"{name}: success={row['success']} similarity={row['similarity']} "
            f"promotions={row['dynamic_synthesis_promotions']} "
            f"rejections={row['dynamic_synthesis_rejections']}"
        )

    summary = {
        "scenarios": len(rows),
        "successes": sum(int(row["success"]) for row in rows),
        "success_rate": 0.0 if not rows else sum(int(row["success"]) for row in rows) / len(rows),
        "llm_calls": sum(int(row["llm_calls"]) for row in rows),
        "dynamic_synthesis_promotions": sum(int(row["dynamic_synthesis_promotions"]) for row in rows),
        "dynamic_synthesis_rejections": sum(int(row["dynamic_synthesis_rejections"]) for row in rows),
    }

    write_csv(output_dir / "episode_metrics.csv", rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote dynamic synthesis probe outputs to {output_dir}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
