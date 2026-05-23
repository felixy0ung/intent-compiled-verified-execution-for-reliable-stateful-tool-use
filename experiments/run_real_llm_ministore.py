from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pctu_pilot.llm_client import OpenAICompatibleClient  # noqa: E402
from pctu_pilot.ministore import MiniStoreEnv, make_tasks  # noqa: E402
from pctu_pilot.real_llm_agents import (  # noqa: E402
    RealProofCarryingAgent,
    RealReactAgent,
    RealRiskAdaptiveVerifiedAgent,
    RealRunConfig,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--api-key", default="not-needed")
    parser.add_argument("--tasks-per-category", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output", default="results/real_llm_ministore.csv")
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["react", "rave"],
        choices=["react", "pctu", "rave"],
        help="Methods to run. PCTU is kept as an ablation; RAVE is the main method.",
    )
    parser.add_argument("--healthcheck-only", action="store_true")
    args = parser.parse_args()

    client = OpenAICompatibleClient(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
    )
    if not client.healthcheck():
        raise SystemExit(
            "No OpenAI-compatible server responded. Start LM Studio, llama.cpp server, "
            "Ollama OpenAI API, or vLLM, then rerun this script with --base-url and --model."
        )
    if args.healthcheck_only:
        print(f"Server is reachable: {args.base_url}")
        return

    tasks = make_tasks(n_per_category=args.tasks_per_category, seed=20260427)
    agents = []
    if "react" in args.methods:
        agents.append(
            RealReactAgent(
                client,
                RealRunConfig(
                    method="Real LLM ReAct",
                    max_steps=args.max_steps,
                    temperature=args.temperature,
                ),
            )
        )
    if "pctu" in args.methods:
        agents.append(
            RealProofCarryingAgent(
                client,
                RealRunConfig(
                    method="Real LLM Proof-Carrying Tool Use",
                    max_steps=args.max_steps,
                    temperature=args.temperature,
                ),
            )
        )
    if "rave" in args.methods:
        agents.append(
            RealRiskAdaptiveVerifiedAgent(
                client,
                RealRunConfig(
                    method="Real LLM Risk-Adaptive Verified Execution",
                    max_steps=args.max_steps,
                    temperature=args.temperature,
                ),
            )
        )

    rows = []
    for agent in agents:
        for task in tasks:
            env = MiniStoreEnv(task)
            rows.append(agent.run(env).to_row())

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} real-LLM episode rows to {output}")


if __name__ == "__main__":
    main()
