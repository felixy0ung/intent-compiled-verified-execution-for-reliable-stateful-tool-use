# AppWorld Official Runner Dev10 Slice, 2026-05-06

## Purpose

This record extends the one-task official AppWorld runner smoke to a small public
`dev10` slice. It checks that the latest `appworld-agents` repository runner can execute
multiple AppWorld 0.2.0 tasks end-to-end with DeepSeek-chat and AppWorld's packaged
evaluator.

This is **not** a full AppWorld leaderboard baseline. It uses a small custom dataset file,
a constrained `max_steps=3` setting, and the official `simplified_react_code_agent`.

## Environment

- Official runner environment: `<CONDA_ROOT>/envs/pctu-appworld-agents`
- `appworld`: 0.2.0.dev0
- `appworld-agents`: 0.1.0.dev0
- Isolated data root: `appworld_020_root`
- Data version: 0.2.0
- Model: `deepseek-v3.2-terminus-exp-without-reasoning`
- Agent: `simplified_react_code_agent`

The existing project `data/` directory was not overwritten. It remains the AppWorld 0.1.x
root used by the active 72-task RAVE slice.

## Dataset

Custom dataset file:

- `appworld_020_root/data/datasets/dev10.txt`

Tasks:

```text
50e1ac9_1
50e1ac9_2
50e1ac9_3
fac291d_1
fac291d_2
fac291d_3
530b157_1
530b157_2
530b157_3
4ec8de5_1
```

The slice contains 10 tasks: one difficulty-1 task, six difficulty-2 tasks, and three
difficulty-3 tasks.

## Command

```bash
set -a
source experiments/deepseek_replication.env
set +a
export DEEPSEEK_API_KEY="$FRONTIER_API_KEY"
export OPENAI_API_KEY="$FRONTIER_API_KEY"

PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/appworld run auto \
  --model-name deepseek-v3.2-terminus-exp-without-reasoning \
  --agent-name simplified_react_code_agent \
  --dataset-name dev10 \
  --with-evaluation \
  --root <PROJECT_ROOT>/appworld_020_root \
  --override '{"config":{"agent":{"max_steps":3,"usage_tracker_config":{"max_cost_per_task":1,"max_cost_overall":10}}}}'
```

## Output

Output directory:

- `appworld_020_root/experiments/outputs/simplified_react_code_agent/deepseek/deepseek-v3.2-terminus-exp-without-reasoning/dev10`

Important artifacts:

- `configs/dev10.json`
- `configs/dev10.jsonnet`
- `tasks/*/logs/api_calls.jsonl`
- `tasks/*/logs/lm_calls.jsonl`
- `tasks/*/logs/environment_io.md`
- `tasks/*/misc/usage.json`
- `evaluations/dev10.json`
- `evaluations/dev10.txt`

## Evaluator Result

| type | task goal completion | scenario goal completion |
| --- | ---: | ---: |
| aggregate | 0.0 | 0.0 |
| difficulty_1 | 0.0 | 0.0 |
| difficulty_2 | 0.0 | 0.0 |
| difficulty_3 | 0.0 | 0.0 |

Task-level result: `0/10`.

The evaluator JSON shows the answer tasks mostly failed with `<<NOT_GIVEN>>`. The
state-changing Venmo/phone tasks did not perform the required mutations; they also did
not delete existing phone messages.

## Usage

Summed over the 10 tasks:

- input cache miss tokens: 51,911
- input cache hit tokens: 82,048
- output tokens: 27,938
- total tokens: 161,897
- mean total tokens per task: 16,189.7
- DeepSeek cost estimate: 0.028566384
- mean DeepSeek cost estimate per task: 0.0028566384

Observed API-call log line counts were 3 for nine tasks and 4 for one task.

## Interpretation

The result confirms that the latest official AppWorld repository-agent runner is usable
for a multi-task slice in the isolated AppWorld 0.2.0 root. The constrained official
`simplified_react_code_agent` baseline is weak on this slice: with `max_steps=3`, it
spends most steps on API discovery, credential lookup, and login/setup, then fails to
produce answers or target state mutations.

This should be cited only as official-runner feasibility plus a constrained 3-step smoke
test. It should not be used as the main official baseline. The default-50-step follow-up
is `results/appworld_official_runner_dev10_full50_20260506.md`: on the same small
official AppWorld 0.2.0 slice, official DeepSeek ReAct-code reaches 90.0 task-goal /
75.0 scenario-goal completion, while deterministic RAVE and RAVE + DeepSeek-chat intent
extraction reach 100.0 / 100.0 after four additional intent machines are registered.
Neither result should be described as a full official AppWorld dev/test or leaderboard
comparison.
