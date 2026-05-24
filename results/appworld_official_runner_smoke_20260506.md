# AppWorld Official Runner Smoke, 2026-05-06

## Purpose

This record checks whether the latest AppWorld repository-agent path is executable after
the previous Git LFS bundle blocker. It is not a full leaderboard baseline. A follow-up
multi-task official-runner check is recorded in
`results/appworld_official_runner_dev10_20260506.md`.

## Environment

- Code checkout: `third_party/appworld-latest`
- Official runner environment: `<CONDA_ROOT>/envs/pctu-appworld-agents`
- `appworld`: 0.2.0.dev0
- `appworld-agents`: 0.1.0.dev0
- Isolated data root: `appworld_020_root`
- Data version: 0.2.0

The existing project `data/` directory was not overwritten because it contains the
0.1.0 AppWorld data used by the active 72-task RAVE slice.

## Setup Checks

The AppWorld Git LFS pointers were replaced with real bundle files using the
`git-lfs` binary from the isolated environment:

```bash
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
git -C third_party/appworld-latest lfs install --local

PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
git -C third_party/appworld-latest lfs pull \
  --include='src/appworld/.source/apps.bundle,src/appworld/.source/tests.bundle,generate/.source/data.bundle,generate/.source/tasks.bundle'
```

The real bundle sizes are:

- `src/appworld/.source/apps.bundle`: 193950 bytes
- `src/appworld/.source/tests.bundle`: 204426 bytes
- `generate/.source/tasks.bundle`: 163959 bytes
- `generate/.source/data.bundle`: 1508806 bytes

`appworld install --repo` then unpacked apps, package tests, task generation, and data
generation sources in `third_party/appworld-latest`. The site-packages install was also
completed by copying the real app/test bundles into the conda environment and running:

```bash
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
APPWORLD_ROOT=<PROJECT_ROOT> \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/appworld install
```

The latest AppWorld runner requires data version 0.2.0, while the RAVE slice uses
AppWorld 0.1.0 data. The 0.2.0 data was therefore downloaded into an isolated root:

```bash
mkdir -p <PROJECT_ROOT>/appworld_020_root
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/appworld download data \
  --version 0.2.0 \
  --root <PROJECT_ROOT>/appworld_020_root
```

The isolated 0.2.0 datasets contain 56 dev tasks, 89 train tasks, 167 test-normal tasks,
and 416 test-challenge tasks.

The end-to-end AppWorld installation verification passed on one task:

```bash
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/appworld verify tasks \
  --include-only-first-n-tasks 1 \
  --root <PROJECT_ROOT>/appworld_020_root
```

Output: `Passed 1/1 tasks`.

## Official Agent Smoke

Command:

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
  --dataset-name dev \
  --task-id 82e2fac_1 \
  --with-evaluation \
  --root <PROJECT_ROOT>/appworld_020_root \
  --override '{"config":{"agent":{"max_steps":3,"usage_tracker_config":{"max_cost_per_task":1,"max_cost_overall":1}}}}'
```

Task:

- `82e2fac_1`: "What is the title of the most-liked song in my Spotify playlists."

Output directory:

- `appworld_020_root/experiments/outputs/simplified_react_code_agent/deepseek/deepseek-v3.2-terminus-exp-without-reasoning/dev`

Important artifacts:

- `configs/dev.json`
- `configs/dev.jsonnet`
- `tasks/82e2fac_1/logs/api_calls.jsonl`
- `tasks/82e2fac_1/logs/lm_calls.jsonl`
- `tasks/82e2fac_1/logs/environment_io.md`
- `tasks/82e2fac_1/logs/logger.log`
- `tasks/82e2fac_1/misc/usage.json`
- `evaluations/on_only_82e2fac_1.json`
- `evaluations/on_only_82e2fac_1.txt`

Evaluator result:

| type | task goal completion | scenario goal completion |
| --- | ---: | ---: |
| aggregate | 0.0 | 0.0 |

Usage on the single task:

- input cache miss tokens: 5980
- input cache hit tokens: 8704
- output tokens: 116
- DeepSeek cost estimate: 0.001966832

## Interpretation

This resolves the earlier claim that the latest official AppWorld repository-agent runner
was blocked by unavailable Git LFS bundles. The runner and packaged evaluator are now
executable in an isolated AppWorld 0.2.0 root.

This does not yet provide a full AppWorld leaderboard or dev/test baseline. The follow-up
constrained `dev10` check reaches 0/10 with `max_steps=3`, and the later default-50-step
`dev10_full50` check reaches 90.0 task-goal / 75.0 scenario-goal completion for official
DeepSeek ReAct-code versus 100.0 / 100.0 for deterministic RAVE and RAVE + DeepSeek-chat
intent extraction after four additional intent machines are registered. The active paper
should still avoid claiming full official repository-agent benchmark coverage until a
substantially larger official-runner baseline is completed on a public dataset split.
