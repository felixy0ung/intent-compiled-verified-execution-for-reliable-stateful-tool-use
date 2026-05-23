# ToolSandbox Kill-Criteria Run

The public ToolSandbox runner is now the primary benchmark gate for
**RAVE / Intent-Compiled Verified Execution**.

```bash
python experiments/run_toolsandbox_kill_criteria.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-3B-Instruct \
  --methods react rave \
  --max-scenarios 30
```

The runner supports:

- `ToolSandbox ReAct`: plain JSON tool-use baseline.
- `ToolSandbox RAVE`: risk-adaptive verified executor with intent compilation,
  argument normalization, precondition repair, and completion detection.
- `ToolSandbox PCTU`: old proof-carrying action-contract ablation.

Outputs are written under `results/<output-dir>/<timestamp>/`:

- `episode_metrics.csv`: per-scenario metrics.
- `summary.csv` / `summary.md`: aggregate comparison.
- `kill_criteria.md`: pass/stop decision.
- `react/`, `rave/`, and optionally `pctu/`: ToolSandbox trajectories.

## Current Main Result

Latest clean result:

`results/toolsandbox_qwen25_3b_rave_30_v3/20260429_011957/`

| method | success | mean similarity | invalid/task | unsafe/task | llm calls/task | token proxy/task |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ReAct | 0.000 | 0.3126 | 1.9000 | 0.000 | 7.1333 | 5502.6667 |
| RAVE | 1.000 | 1.0000 | 0.0000 | 0.000 | 0.2667 | 69.8333 |

Decision: `CONTINUE`.

## Decision Rule

The default kill criteria are:

- RAVE reduces invalid executed tool calls by at least 25%.
- RAVE improves exact ToolSandbox success rate by at least 5 percentage points.
- RAVE does not increase LLM calls or token proxy by more than 2x.
- RAVE does not increase minefield-triggered unsafe state changes.

If these checks fail on a public benchmark slice, stop making broad claims from the
current method and either strengthen RAVE or narrow the claim.

## Required Next Runs

- Expand beyond the current default 30 single-turn/stateful scenarios.
- Include multi-turn and insufficient-information ToolSandbox categories.
- Add RAVE ablations: no intent compiler, no argument normalizer, no precondition repair,
  no completion detector.
- Re-run with at least one stronger and one weaker local/open model.
