# AppWorld Official dev10_full50 Runner and RAVE Comparison

Date: 2026-05-06 CST.

This record addresses the concern that the earlier official AppWorld `dev10` result used
a constrained `max_steps=3` setting. It reruns the latest official `appworld-agents`
`simplified_react_code_agent` with its default 50-step budget on the same 10-task
AppWorld 0.2.0 slice, then evaluates a matching RAVE deterministic runtime after adding
four typed intent machines for the slice.

This is still a small official-runner slice, not full AppWorld leaderboard coverage.

## Environment

- Official AppWorld runner env:
  `<CONDA_ROOT>/envs/pctu-appworld-agents`
- AppWorld root:
  `<PROJECT_ROOT>/appworld_020_root`
- Dataset:
  `appworld_020_root/data/datasets/dev10_full50.txt`
- Dataset task ids:
  `50e1ac9_1`, `50e1ac9_2`, `50e1ac9_3`, `fac291d_1`, `fac291d_2`,
  `fac291d_3`, `530b157_1`, `530b157_2`, `530b157_3`, `4ec8de5_1`

## Compared Runs

### Official DeepSeek ReAct-code Agent

Command:

```bash
# Source a private DeepSeek environment file that sets the API variables required by AppWorld.

PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/appworld run auto \
  --model-name deepseek-v3.2-terminus-exp-without-reasoning \
  --agent-name simplified_react_code_agent \
  --dataset-name dev10_full50 \
  --with-evaluation \
  --root <PROJECT_ROOT>/appworld_020_root \
  --override '{"config":{"agent":{"usage_tracker_config":{"max_cost_per_task":1,"max_cost_overall":10}}}}'
```

Outputs:

- `appworld_020_root/experiments/outputs/simplified_react_code_agent/deepseek/deepseek-v3.2-terminus-exp-without-reasoning/dev10_full50`
- `evaluations/dev10_full50.json`
- `evaluations/dev10_full50.txt`

### RAVE Typed Intent Runtime

Newly registered `IntentMachine`s:

- `appworld_spotify_top_played_genre_titles`
- `appworld_spotify_count_unique_library_songs`
- `appworld_venmo_pay_grocery_from_text_and_notify`
- `appworld_spotify_count_recent_release_library_songs`

Deterministic compiler command:

```bash
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python \
  experiments/run_appworld_rave_slice.py \
  --appworld-root <PROJECT_ROOT>/appworld_020_root \
  --output-root results/appworld_rave_official_dev10_full50 \
  --experiment-name rave_official_dev10_full50 \
  --task-ids 50e1ac9_1 50e1ac9_2 50e1ac9_3 fac291d_1 fac291d_2 fac291d_3 530b157_1 530b157_2 530b157_3 4ec8de5_1 \
  --agent deterministic \
  --timeout-seconds 60 \
  --flush-each-task
```

Packaged evaluator command:

```bash
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
PYTHONPATH=<PROJECT_ROOT>/src \
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python -m appworld.cli evaluate \
  rave_official_dev10_full50 dev10_full50 \
  --root <PROJECT_ROOT>/appworld_020_root
```

Outputs:

- `results/appworld_rave_official_dev10_full50/20260506_015002`
- `appworld_020_root/experiments/outputs/rave_official_dev10_full50/evaluations/dev10_full50.json`
- `appworld_020_root/experiments/outputs/rave_official_dev10_full50/evaluations/dev10_full50.txt`

DeepSeek intent-extraction command:

```bash
set -a
source experiments/deepseek_replication.env
set +a

PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python \
  experiments/run_appworld_rave_slice.py \
  --appworld-root <PROJECT_ROOT>/appworld_020_root \
  --output-root results/appworld_rave_official_dev10_full50_llm_intent_deepseek_chat \
  --experiment-name rave_official_dev10_full50_llm_intent_deepseek_chat \
  --task-ids 50e1ac9_1 50e1ac9_2 50e1ac9_3 fac291d_1 fac291d_2 fac291d_3 530b157_1 530b157_2 530b157_3 4ec8de5_1 \
  --agent llm-intent \
  --timeout-seconds 60 \
  --client-timeout-seconds 120 \
  --temperature 0 \
  --max-tokens 512 \
  --flush-each-task
```

Outputs:

- `results/appworld_rave_official_dev10_full50_llm_intent_deepseek_chat/20260506_015233`
- `appworld_020_root/experiments/outputs/rave_official_dev10_full50_llm_intent_deepseek_chat/evaluations/dev10_full50.json`
- `appworld_020_root/experiments/outputs/rave_official_dev10_full50_llm_intent_deepseek_chat/evaluations/dev10_full50.txt`

## Packaged Evaluator Results

| method | task goal completion | scenario goal completion | task-level success |
| --- | ---: | ---: | ---: |
| RAVE deterministic runtime | 100.0 | 100.0 | 10/10 |
| RAVE + DeepSeek-chat intent extraction | 100.0 | 100.0 | 10/10 |
| Official DeepSeek `simplified_react_code_agent`, default 50 steps | 90.0 | 75.0 | 9/10 |
| Official DeepSeek `simplified_react_code_agent`, constrained 3 steps | 0.0 | 0.0 | 0/10 |

The constrained 3-step row is retained only as smoke/feasibility evidence from
`results/appworld_official_runner_dev10_20260506.md`; it should not be used as the main
official baseline.

Difficulty breakdown:

| method | difficulty 1 | difficulty 2 | difficulty 3 |
| --- | ---: | ---: | ---: |
| RAVE deterministic runtime | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 |
| RAVE + DeepSeek-chat intent extraction | 100.0 / 100.0 | 100.0 / 100.0 | 100.0 / 100.0 |
| Official DeepSeek ReAct-code, 50 steps | 100.0 / 100.0 | 100.0 / 100.0 | 66.7 / 0.0 |

Cells are task-goal / scenario-goal completion.

## Cost and Call Counts

| method | tasks | API calls total | API calls/task | LLM calls total | tokens total | estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RAVE deterministic runtime | 10 | 416 | 41.6 | 0 | 2,416 token-proxy | 0 |
| RAVE + DeepSeek-chat intent extraction | 10 | 416 | 41.6 | 10 | 39,466 | not separately metered by local runner |
| Official DeepSeek ReAct-code, 50 steps | 10 | 473 | 47.3 | 174 | 1,400,122 | 0.088640972 |

RAVE uses one verified code execution per task. The token-proxy value is the local script's
instruction+compiled-code word-count proxy, not billed LLM tokens.

Official DeepSeek ReAct-code token range: 67,078 to 209,615 tokens/task; mean
140,012.2 tokens/task. Cost mean: 0.0088640972 USD/task.

## Failure Mode

The default 50-step official ReAct-code agent fails only `530b157_3`. The packaged
evaluator reports that the added Venmo transaction amount is `37.0` while the expected
grocery amount is `72`. This is a semantic state-change error in a multi-amount phone
conversation. RAVE's compiler grounds the grocery amount from the earlier "It was $..."
message and passes all three grocery-payment variants.

## Interpretation

This result materially improves the AppWorld evidence but also changes the earlier
baseline framing:

- The earlier `max_steps=3` official `dev10` result was a constrained smoke test and is
  not the relevant performance baseline.
- With the default 50-step budget, the official DeepSeek ReAct-code baseline is strong on
  this small slice but still misses one difficult semantic state-change task and consumes
  substantial LLM tokens.
- RAVE is now directly comparable on this same official AppWorld 0.2.0 slice:
  deterministic compilers and DeepSeek-chat intent extraction both reach 100.0 task-goal
  and scenario-goal completion after registering four additional typed intent machines.
- This remains small-slice evidence. It strengthens the paper's cost/safety argument but
  does not replace a broad official AppWorld dev/test or leaderboard comparison.
