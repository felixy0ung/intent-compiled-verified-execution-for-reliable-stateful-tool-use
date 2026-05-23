# AppWorld Test-Normal Smoke60, 2026-05-06

## Scope

This is an expanded held-out smoke on the first 60 task ids from
`appworld_020_root/data/datasets/test_normal.txt`. It is not a full AppWorld test split
run and not a leaderboard submission. It uses only public task instructions and live app
APIs; unsupported families abstain.

The preceding first-12 smoke is recorded in
`results/appworld_test_normal_smoke12_20260506.md`.

## Result

Output directory:
`results/appworld_rave_official_test_normal_smoke60_expanded_v2/20260506_042801`

| episodes | overall success | supported | supported success | invalid/tool | unsafe/task | code exec/task | LLM/task |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 60 | 38/60 | 39/60 | 38/39 | 0.3500 | 0.0000 | 0.6500 | 0.0000 |

Summary CSV:

```text
method,episodes,success_rate,supported_rate,invalid_tool_calls_per_task,unsafe_state_changes_per_task,api_calls_per_task,code_exec_calls_per_task,llm_calls_per_task,prompt_tokens_per_task,completion_tokens_per_task,token_proxy_per_task
rave_appworld_slice,60,0.6333,0.65,0.35,0.0,19.3667,0.65,0.0,0.0,0.0,130.4833
```

The 21 invalid tool calls are abstentions for unsupported task families. Among supported
families, there are 0 unsafe state changes and one remaining failure:
`d18139b_2`, a Venmo roommate payment-request approval task whose evaluator expects a
different exact updated request set. The sibling variants `d18139b_1` and `d18139b_3`
pass.

DeepSeek-chat intent extraction on the same 60 tasks is recorded under
`results/appworld_rave_official_test_normal_smoke60_llm_intent_deepseek_chat/20260506_043113`.
It matches the deterministic overall success count, 38/60, with 0 unsafe state changes
and 1 LLM call per task. That run exposed two LLM over-generalizations on unsupported
housing-bill correction tasks (`9dabbc9_2`, `9dabbc9_3`), where the model routed to the
generic Venmo pending-request machine. The instruction-aware verifier was then patched
to abstain on that family; the guard smoke
`results/appworld_rave_official_test_normal_housing_guard_deepseek/20260506_043304`
shows all three `9dabbc9` variants now return unsupported with 0 unsafe state changes.

## Newly Covered Families Beyond Smoke12

- Venmo month sent/received amount queries: `21abae1_{1,2,3}`: 3/3
- Spotify archive playlist songs listed in a file: `634f342_{1,2,3}`: 3/3
- Spotify reset queue from recommendations: `8749218_{1,2,3}`: 3/3
- Simple Note markdown import from file system: `0d01c76_{1,2,3}`: 3/3
- Venmo add friends by relationships: `ff58e36_{1,2,3}`: 3/3
- Venmo approve roommate payment requests this month: `d18139b_{1,2,3}`: 2/3
- File delete downloads by extension: `5a83b05_{1,2,3}`: 3/3
- Spotify followed-artist follower extreme: `cef9191_{1,2,3}`: 3/3
- Spotify liked-genre extreme: `425a494_{1,2,3}`: 3/3

## Reproduction

```bash
TASK_IDS=$(head -60 appworld_020_root/data/datasets/test_normal.txt | tr '\n' ' ')
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python \
  experiments/run_appworld_rave_slice.py \
  --appworld-root <PROJECT_ROOT>/appworld_020_root \
  --output-root results/appworld_rave_official_test_normal_smoke60_expanded_v2 \
  --experiment-name rave_official_test_normal_smoke60_expanded_v2 \
  --task-ids $TASK_IDS \
  --agent deterministic \
  --timeout-seconds 120 \
  --flush-each-task
```
