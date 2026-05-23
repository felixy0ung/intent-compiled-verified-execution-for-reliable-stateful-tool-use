# AppWorld Test-Normal Smoke12, 2026-05-06

## Scope

This is a low-cost held-out smoke on the first 12 task ids from
`appworld_020_root/data/datasets/test_normal.txt`. It is not a full AppWorld test split
run and not a leaderboard submission.

The task families are:

- Venmo friend-list synchronization to phone friends: `3d9a636_{1,2,3}`
- Spotify queue filtering by liked status: `fd1f8fa_{1,2,3}`
- Spotify navigation until liked/downloaded song: `325d6ec_{1,2,3}`
- File-system meeting-file reorganization: `29a7b7e_{1,2,3}`

The first smoke before adding these machines is retained at
`results/appworld_rave_official_test_normal_smoke12/20260506_040346` and had
`supported_rate=0.0`, `success_rate=0.0`, and 1 invalid tool call per task.

After registering four new AppWorld `IntentMachine`s, the deterministic RAVE row is:

| output directory | episodes | success | supported | invalid/tool | unsafe/task | code exec/task | LLM/task |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `results/appworld_rave_official_test_normal_smoke12_expanded_v2/20260506_041455` | 12 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |

Summary CSV:

```text
method,episodes,success_rate,supported_rate,invalid_tool_calls_per_task,unsafe_state_changes_per_task,api_calls_per_task,code_exec_calls_per_task,llm_calls_per_task,prompt_tokens_per_task,completion_tokens_per_task,token_proxy_per_task
rave_appworld_slice,12,1.0,1.0,0.0,0.0,25.0,1.0,0.0,0.0,0.0,169.8333
```

Per-task outcome:

```text
3d9a636_1 appworld_venmo_reset_friends_to_phone_friends success=1 invalid=0 unsafe=0
3d9a636_2 appworld_venmo_reset_friends_to_phone_friends success=1 invalid=0 unsafe=0
3d9a636_3 appworld_venmo_reset_friends_to_phone_friends success=1 invalid=0 unsafe=0
fd1f8fa_1 appworld_spotify_filter_queue_by_liked_status success=1 invalid=0 unsafe=0
fd1f8fa_2 appworld_spotify_filter_queue_by_liked_status success=1 invalid=0 unsafe=0
fd1f8fa_3 appworld_spotify_filter_queue_by_liked_status success=1 invalid=0 unsafe=0
325d6ec_1 appworld_spotify_navigate_until_private_status success=1 invalid=0 unsafe=0
325d6ec_2 appworld_spotify_navigate_until_private_status success=1 invalid=0 unsafe=0
325d6ec_3 appworld_spotify_navigate_until_private_status success=1 invalid=0 unsafe=0
29a7b7e_1 appworld_file_reorganize_dated_meeting_files success=1 invalid=0 unsafe=0
29a7b7e_2 appworld_file_reorganize_dated_meeting_files success=1 invalid=0 unsafe=0
29a7b7e_3 appworld_file_reorganize_dated_meeting_files success=1 invalid=0 unsafe=0
```

## Reproduction

```bash
TASK_IDS=$(head -12 appworld_020_root/data/datasets/test_normal.txt | tr '\n' ' ')
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python \
  experiments/run_appworld_rave_slice.py \
  --appworld-root <PROJECT_ROOT>/appworld_020_root \
  --output-root results/appworld_rave_official_test_normal_smoke12_expanded_v2 \
  --experiment-name rave_official_test_normal_smoke12_expanded_v2 \
  --task-ids $TASK_IDS \
  --agent deterministic \
  --timeout-seconds 90 \
  --flush-each-task
```

