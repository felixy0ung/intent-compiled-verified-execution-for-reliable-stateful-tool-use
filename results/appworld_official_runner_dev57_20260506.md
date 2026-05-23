# AppWorld Official dev57 RAVE Runtime Evidence

Date: 2026-05-06 CST.

This record extends the AppWorld evidence from the earlier `dev10_full50` slice to the
complete official AppWorld 0.2.0 `dev.txt` split available in the isolated local root.
The run evaluates RAVE deterministic typed-intent compilers, RAVE with DeepSeek-chat
intent extraction, and the official repository DeepSeek `simplified_react_code_agent`
on the same 57 official dev tasks using AppWorld's packaged evaluator. It does not claim
leaderboard coverage because this is a local official dev split, not the held-out test
split or public leaderboard protocol.

## Environment

- AppWorld runner env: `<CONDA_ROOT>/envs/pctu-appworld-agents`
- AppWorld root: `<PROJECT_ROOT>/appworld_020_root`
- Dataset: `appworld_020_root/data/datasets/dev.txt`
- Dataset size: 57 tasks
- RAVE source: `src/pctu_pilot/appworld_agents.py`
- Official ReAct-code baseline: AppWorld Agents
  `simplified_react_code_agent/deepseek/deepseek-v3.2-terminus-exp-without-reasoning`

## Added Intent Machines

To cover the remaining official dev task families, the AppWorld RAVE binding now registers
seven additional intent machines and extends the release-year counter:

- `appworld_spotify_navigate_until_artist`
- `appworld_venmo_like_transactions_by_relationship_period`
- `appworld_venmo_manager_meal_total_from_social_feed`
- `appworld_venmo_sum_transaction_likes`
- `appworld_file_prefix_and_move_old_files`
- `appworld_spotify_current_artist_followers`
- `appworld_simple_note_export_markdown`
- extended `appworld_spotify_count_recent_release_library_songs` for this-year and before-this-year variants

The handlers use live AppWorld APIs through the runtime `apis` object. They do not read
compiled solutions, ground-truth files, public/private task data, or task JSON to choose
actions.

## Commands

Deterministic RAVE:

```bash
TASK_IDS=$(tr '\n' ' ' < appworld_020_root/data/datasets/dev.txt)
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python \
  experiments/run_appworld_rave_slice.py \
  --appworld-root <PROJECT_ROOT>/appworld_020_root \
  --output-root results/appworld_rave_official_dev57_final \
  --experiment-name rave_official_dev57_final \
  --task-ids $TASK_IDS \
  --agent deterministic \
  --timeout-seconds 90 \
  --flush-each-task
```

Packaged evaluator:

```bash
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
PYTHONPATH=<PROJECT_ROOT>/src \
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python -m appworld.cli evaluate \
  rave_official_dev57_final dev \
  --root <PROJECT_ROOT>/appworld_020_root
```

DeepSeek-chat intent extraction:

```bash
set -a
source experiments/deepseek_replication.env
set +a

TASK_IDS=$(tr '\n' ' ' < appworld_020_root/data/datasets/dev.txt)
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python \
  experiments/run_appworld_rave_slice.py \
  --appworld-root <PROJECT_ROOT>/appworld_020_root \
  --output-root results/appworld_rave_official_dev57_final_llm_intent_deepseek_chat \
  --experiment-name rave_official_dev57_final_llm_intent_deepseek_chat \
  --task-ids $TASK_IDS \
  --agent llm-intent \
  --timeout-seconds 90 \
  --client-timeout-seconds 180 \
  --temperature 0 \
  --max-tokens 512 \
  --flush-each-task
```

Official DeepSeek ReAct-code baseline:

```bash
cp appworld_020_root/data/datasets/dev.txt \
  appworld_020_root/data/datasets/dev57_full50.txt

# Source a private DeepSeek environment file that sets the API variables required by AppWorld.

PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/appworld run auto \
  --model-name deepseek-v3.2-terminus-exp-without-reasoning \
  --agent-name simplified_react_code_agent \
  --dataset-name dev57_full50 \
  --with-evaluation \
  --root <PROJECT_ROOT>/appworld_020_root \
  --override '{"config":{"agent":{"usage_tracker_config":{"max_cost_per_task":1,"max_cost_overall":10}}}}'
```

## Outputs

- Deterministic local rows: `results/appworld_rave_official_dev57_final/20260506_021705`
- Deterministic packaged evaluator:
  `appworld_020_root/experiments/outputs/rave_official_dev57_final/evaluations/dev.{json,txt}`
- DeepSeek intent local rows:
  `results/appworld_rave_official_dev57_final_llm_intent_deepseek_chat/20260506_021940`
- DeepSeek intent packaged evaluator:
  `appworld_020_root/experiments/outputs/rave_official_dev57_final_llm_intent_deepseek_chat/evaluations/dev.{json,txt}`
- Official DeepSeek ReAct-code packaged evaluator:
  `appworld_020_root/experiments/outputs/simplified_react_code_agent/deepseek/deepseek-v3.2-terminus-exp-without-reasoning/dev57_full50/evaluations/dev57_full50.{json,txt}`

## Results

| method | tasks | packaged task-goal | packaged scenario-goal | local task success | invalid tool calls/task | unsafe state changes/task | LLM calls/task | prompt tokens/task | completion tokens/task |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| RAVE deterministic typed runtime | 57 | 100.0 | 100.0 | 57/57 | 0.0351 | 0.0000 | 0.0 | 0.0 | 0.0 |
| RAVE + DeepSeek-chat intent extraction | 57 | 100.0 | 100.0 | 57/57 | 0.0351 | 0.0000 | 1.0 | 4,947.0 | 35.386 |
| Official DeepSeek `simplified_react_code_agent`, default 50 steps | 57 | 79.0 | 73.7 | 45/57 | not separately aggregated | not separately aggregated | 15.4211 | 107,800.6 | 5,401.9 |

The packaged evaluator reports 100.0 / 100.0 for aggregate, difficulty 1, difficulty 2,
and difficulty 3 for both RAVE rows.

For the official DeepSeek ReAct-code row, the packaged evaluator reports aggregate
79.0 task-goal / 73.7 scenario-goal completion, with difficulty groups 83.3 / 80.0,
70.8 / 62.5, and 100.0 / 100.0. The run completed all 57 tasks in 4553.6 seconds
(75.9 minutes). Aggregating the official runner task logs gives 879 LLM calls,
6,452,544 total tokens, 113,202.5 tokens per task, and estimated DeepSeek cost
0.413653436. The task-level success count in the evaluator JSON is 45/57.

The two residual local invalid API attempts come from two Venmo phone-number payment tasks
where the public Venmo card list exposes card metadata but not card balances. RAVE tries a
non-expired card, receives an insufficient-balance API failure, and then succeeds with the
next public card. We attempted to query card balance through the AppWorld tool wrapper, but
that private admin API is not exposed. The residual cost is 2 failed API attempts over 57
tasks, with no unsafe state-change failures.

## Relation to Official ReAct Baseline

The earlier official AppWorld runner record remains `results/appworld_official_runner_dev10_full50_20260506.md`:
on a 10-task official `dev10_full50` slice, official DeepSeek `simplified_react_code_agent`
with default 50-step budget reached 90.0 task-goal / 75.0 scenario-goal completion with
174 LLM calls and 1,400,122 tokens, while RAVE deterministic and RAVE + DeepSeek-chat
intent extraction reached 100.0 / 100.0 on the same slice.

For the full 57-task official dev split, this record now establishes a same-split local
official ReAct-code comparison. It is still not leaderboard coverage because it does not
run on the held-out AppWorld test split or through a public leaderboard submission.
