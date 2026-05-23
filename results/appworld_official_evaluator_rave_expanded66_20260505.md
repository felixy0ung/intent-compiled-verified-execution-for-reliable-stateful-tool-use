# AppWorld Official Evaluator Check, 2026-05-05

This record re-evaluates the targeted RAVE AppWorld slice with AppWorld's packaged
evaluator, rather than only the local experiment summary code.

## Dataset

- Dataset file: `data/datasets/rave_expanded66.txt`
- Episodes: 66 tasks, matching the active AppWorld table slice.
- Evaluator command pattern:

```bash
APPWORLD_ROOT=<PROJECT_ROOT> \
<CONDA_ROOT>/envs/pctu-appworld/bin/python -m appworld.cli evaluate \
  <experiment_output_name> rave_expanded66 \
  --root <PROJECT_ROOT>
```

The evaluator writes reports under
`experiments/outputs/<experiment_output_name>/evaluations/rave_expanded66.{json,txt}`.

## Aggregate Results

| experiment output | task completion | scenario completion | report |
| --- | ---: | ---: | --- |
| `rave_appworld_expanded66` | 100.0 | 100.0 | `experiments/outputs/rave_appworld_expanded66/evaluations/rave_expanded66.txt` |
| `rave_appworld_qwen25_3b_intent_expanded66` | 100.0 | 100.0 | `experiments/outputs/rave_appworld_qwen25_3b_intent_expanded66/evaluations/rave_expanded66.txt` |
| `rave_appworld_deepseek_chat_intent_expanded66` | 100.0 | 100.0 | `experiments/outputs/rave_appworld_deepseek_chat_intent_expanded66/evaluations/rave_expanded66.txt` |
| `rave_appworld_deepseek_reasoner_intent_expanded66` | 100.0 | 100.0 | `experiments/outputs/rave_appworld_deepseek_reasoner_intent_expanded66/evaluations/rave_expanded66.txt` |
| `appworld_direct_code_qwen25_3b_expanded66` | 0.0 | 0.0 | `experiments/outputs/appworld_direct_code_qwen25_3b_expanded66/evaluations/rave_expanded66.txt` |
| `appworld_code_repair_qwen25_3b_expanded66` | 0.0 | 0.0 | `experiments/outputs/appworld_code_repair_qwen25_3b_expanded66/evaluations/rave_expanded66.txt` |
| `appworld_react_code_qwen25_3b_expanded66` | 0.0 | 0.0 | `experiments/outputs/appworld_react_code_qwen25_3b_expanded66/evaluations/rave_expanded66.txt` |
| `appworld_direct_code_expanded66` | 6.1 | 0.0 | `experiments/outputs/appworld_direct_code_expanded66/evaluations/rave_expanded66.txt` |
| `appworld_code_repair_deepseek_chat_combined66` | 28.8 | 22.7 | `experiments/outputs/appworld_code_repair_deepseek_chat_combined66/evaluations/rave_expanded66.txt` |
| `appworld_react_code_deepseek_chat_combined66` | 27.3 | 0.0 | `experiments/outputs/appworld_react_code_deepseek_chat_combined66/evaluations/rave_expanded66.txt` |

These official evaluator percentages match the task-level success counts reported in the
paper table: 66/66 for the RAVE runtime rows, 0/66 for local Qwen code baselines, 4/66
for DeepSeek direct code, 19/66 for DeepSeek code repair, and 18/66 for DeepSeek
multi-step code-observation.

## Hosted Combined Output Assembly

The hosted DeepSeek repair/ReAct evaluator outputs are assembled from task-level shard
directories under `experiments/outputs/`:

- `experiments/outputs/appworld_code_repair_deepseek_chat_combined66`
- `experiments/outputs/appworld_react_code_deepseek_chat_combined66`

Each combined directory contains 66 unique task directories. The corresponding CSV metric
summaries remain under:

- `results/appworld_llm_code_repair_deepseek_chat_combined66/20260505_143100`
- `results/appworld_llm_react_code_deepseek_chat_combined66/20260505_143100`

The official AppWorld repository baseline runner was attempted separately in
`results/appworld_official_agent_attempt_20260505.md`. Its Python package stack installed
and imported in an isolated environment, but execution was blocked because the latest
AppWorld app/test bundles were Git LFS pointers and the real LFS objects could not be
downloaded from GitHub in this environment. Therefore these rows should be described as
packaged-evaluator checks plus same-slice local/hosted baselines, not as official
repository-agent or full leaderboard-agent comparisons.

Follow-up: the Git LFS blocker was later resolved and the official runner executed a
one-task DeepSeek-chat `simplified_react_code_agent` smoke, a constrained `dev10`
smoke, and a default-50-step `dev10_full50` slice in an isolated AppWorld 0.2.0 root; see
`results/appworld_official_runner_smoke_20260506.md`,
`results/appworld_official_runner_dev10_20260506.md`, and
`results/appworld_official_runner_dev10_full50_20260506.md`. This historical 66-task
evaluator note remains separate from those official-runner checks.
