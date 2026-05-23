# AppWorld Test-Normal Smoke120, 2026-05-06

## Scope

This is an expanded held-out smoke on the first 120 task ids from
`appworld_020_root/data/datasets/test_normal.txt`. It is not a full AppWorld test split
run and not a leaderboard submission. It uses only public task instructions and live app
APIs; unsupported families abstain.

The preceding first-60 smoke is recorded in
`results/appworld_test_normal_smoke60_20260506.md`.

## Result

Latest deterministic compiler/runtime output directory:
`results/appworld_rave_official_test_normal_smoke120_d18139b_card_path_v67/20260507_030820`

| episodes | overall success | supported | supported success | invalid/tool | unsafe/task | code exec/task | LLM/task |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 120 | 117/120 | 117/120 | 117/117 | 0.0250 | 0.0000 | 0.9750 | 0.0000 |

Summary CSV:

```text
method,episodes,success_rate,supported_rate,invalid_tool_calls_per_task,unsafe_state_changes_per_task,api_calls_per_task,code_exec_calls_per_task,llm_calls_per_task,prompt_tokens_per_task,completion_tokens_per_task,token_proxy_per_task
rave_appworld_slice,120,0.975,0.975,0.025,0.0,35.6,0.975,0.0,0.0,0.0,270.8667
```

The 3 invalid tool calls are the three abstentions/no-action blocks for unsupported
`3b8fb7a_{1,2,3}` vacation-settlement tasks. The named-payment family
`2c544f9_{1,2,3}` now succeeds without failed API probes by adding a public supervisor
card before the transfer when the Venmo balance is insufficient. The roommate payment
request approval family `d18139b_{1,2,3}` now succeeds without failed card probes after
rotating successful non-expired cards instead of reusing a depleted card first. Among
supported families, there are 0 unsafe state changes and 0 remaining supported failures.

Latest completed DeepSeek-chat intent-extraction companion output directory:
`results/appworld_rave_official_test_normal_smoke120_llm_intent_deepseek_chat_d18139b_card_path_v68/20260507_031027`

| episodes | overall success | supported | supported success | invalid/tool | unsafe/task | code exec/task | LLM/task |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 120 | 117/120 | 117/120 | 117/117 | 0.0250 | 0.0000 | 0.9750 | 1.0000 |

Companion summary CSV:

```text
method,episodes,success_rate,supported_rate,invalid_tool_calls_per_task,unsafe_state_changes_per_task,api_calls_per_task,code_exec_calls_per_task,llm_calls_per_task,prompt_tokens_per_task,completion_tokens_per_task,token_proxy_per_task
rave_appworld_llm_intent_slice,120,0.975,0.975,0.025,0.0,35.6,0.975,1.0,11336.2083,34.3667,11370.575
```

The DeepSeek v68 row reaches the same 117/120 overall success and 117/120 supported
coverage as deterministic v67. A strict instruction-aware verifier blocks unsupported
vacation-settlement tasks in the `3b8fb7a` family before code execution. They are counted
as invalid no-action blocks, while unsafe state changes remain 0.

## Local Full `test_normal.txt` Continuation

The local AppWorld 0.2.0 `test_normal.txt` file contains 167 task ids. After the first-120
run above, the remaining 121--167 continuation was run under:

- deterministic:
  `results/appworld_rave_official_test_normal_smoke121_167_d18139b_card_path_v69/20260507_032529`
- DeepSeek-chat intent extraction:
  `results/appworld_rave_official_test_normal_smoke121_167_llm_intent_deepseek_chat_d18139b_card_path_v70/20260507_032651`

Both continuation rows reach 47/47 success, 47/47 supported success, 0 invalid tool calls,
and 0 unsafe state changes. Combined file-level summaries are stored under
`results/appworld_rave_official_test_normal_full167_d18139b_card_path_20260507/`.

| agent | episodes | overall success | supported | supported success | invalid/tool | unsafe/task | LLM/task |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic | 167 | 164/167 | 164/167 | 164/164 | 0.0180 | 0.0000 | 0.0000 |
| DeepSeek-chat intent | 167 | 164/167 | 164/167 | 164/164 | 0.0180 | 0.0000 | 1.0000 |

The only failures in the local full-file summary are the protected
`3b8fb7a_{1,2,3}` vacation-settlement abstentions. This is a local file-level AppWorld
0.2.0 result, not a public leaderboard submission.

A preceding DeepSeek-chat intent extraction run on the same first 120 tasks exposed five
LLM over-generalizations on unsupported tasks: offline Spotify playback tasks
`0de03ea_1` and `0de03ea_3`, and named carpool Venmo request tasks
`9ef798c_{1,2,3}`. The offline playback family is now covered by a dedicated typed
machine that requires a unique public library collection with enough already downloaded
songs; the named carpool Venmo request family is also covered by a dedicated typed
machine.

After the earlier run, the instruction-aware verifier and intent prompt were patched to make
unsupported families abstain rather than execute a similar-looking machine. The
guard smoke
`results/appworld_rave_official_test_normal_llm_guard_deepseek_0de03ea_9ef798c/20260506_044730`
shows all six `0de03ea`/`9ef798c` variants return unsupported with 0 unsafe state
changes under the earlier registry; the latest registry subsequently adds safe
machines for `0de03ea_{1,2,3}` and `9ef798c_{1,2,3}`.

## Newly Covered Families Beyond Smoke60

- Spotify playlist artist count extremes: `09b0ee6_{1,2,3}`: 3/3
- Venmo year-to-date bill payment totals: `552869a_{1,2,3}`: 3/3
- Venmo add/sync friends from current-month transaction counterparties:
  `522e5e5_{1,2,3}` and `c77c005_{1,2,3}`: 6/6
- Spotify public liked-library playlist sharing: `652485c_{1,2,3}`: 3/3
- Venmo request money from contact: `024c982_{1,2,3}`: 3/3
- Phone relationship message sending: `13547f5_{1,2,3}`: 3/3
- Spotify play released-year song from library/album/playlists: `1150ed6_{1,2,3}`: 3/3
- Phone wake-alarm snooze update: `31dc501_{1,2,3}`: 3/3
- Simple Note bucket-list status counts: `7847649_{1,2,3}`: 3/3
- Simple Note workout-duration summaries: `afc4005_{1,2,3}`: 3/3
- Simple Note random quote retrieval: `a30375d_{1,2,3}`: 3/3
- Simple Note today habit-log creation: `d6ac34d_{1,2,3}`: 3/3
- Simple Note habit-tracker CSV export: `f323bae_{1,2,3}`: 3/3
- Venmo named payment with no-probe public-card add path: `2c544f9_{1,2,3}`: 3/3, with
  0 invalid API attempts after the no-probe public-card add path
- Venmo named carpool request approval: `9ef798c_{1,2,3}`: 3/3
- Venmo housing-bill request correction: `9dabbc9_{1,2,3}`: 3/3
- Venmo approve requests and withdraw balance: `ccf4b82_{1,2,3}`: 3/3
- Spotify playlist from recent Simple Note song list: `d194965_{1,2,3}`: 3/3
- Simple Note liked-song release-month fill from Spotify: `6f4b9a5_{1,2,3}`: 3/3
- Venmo birthday child payment plus phone text: `270f1ff_{1,2,3}`: 3/3
- Venmo sent-request correction from yesterday evening: `90adc3f_{1,2,3}`: 3/3
- File reunion RSVP CSV update from latest phone replies: `b9c5c9a_{1,2,3}`: 3/3
- Spotify roadtrip playlist update from phone suggestions: `042a9fc_{1,2,3}`: 3/3
- Venmo roommate dinner settlement with taxi requests and food payment:
  `2d9f728_{1,2,3}`: 3/3
- Spotify offline playback from a unique sufficiently downloaded album/playlist:
  `0de03ea_{1,2,3}`: 3/3

The dedicated offline Spotify playback smoke is recorded under
`results/appworld_rave_official_test_normal_0de03ea_offline_spotify_v51/20260506_140740`
and reaches 3/3 success with 0 invalid tool calls and 0 unsafe state changes. Its
DeepSeek-chat intent-extraction companion under
`results/appworld_rave_official_test_normal_0de03ea_offline_spotify_llm_intent_deepseek_v52/20260506_140754`
also reaches 3/3 with 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
changes.

The dedicated roommate dinner settlement smoke is recorded under
`results/appworld_rave_official_test_normal_2d9f728_roommate_dinner_v46/20260506_134252`
and reaches 3/3 success with 0 invalid tool calls and 0 unsafe state changes. Its
DeepSeek-chat intent-extraction companion under
`results/appworld_rave_official_test_normal_2d9f728_roommate_dinner_llm_intent_deepseek_v47/20260506_134307`
also reaches 3/3 with 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
changes.

The dedicated phone playlist suggestion smoke is recorded under
`results/appworld_rave_official_test_normal_042a9fc_phone_playlist_v42/20260506_132749`
and reaches 3/3 success with 0 invalid tool calls and 0 unsafe state changes. Its
DeepSeek-chat intent-extraction companion under
`results/appworld_rave_official_test_normal_042a9fc_phone_playlist_llm_intent_deepseek_v43/20260506_132808`
also reaches 3/3 with 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
changes.

The dedicated reunion RSVP smoke is recorded under
`results/appworld_rave_official_test_normal_b9c5c9a_reunion_rsvp_v36/20260506_130212`
and reaches 3/3 success with 0 invalid tool calls and 0 unsafe state changes. Its
DeepSeek-chat intent-extraction companion under
`results/appworld_rave_official_test_normal_b9c5c9a_reunion_rsvp_llm_intent_deepseek_v37/20260506_130228`
also reaches 3/3 with 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
changes.

The dedicated sent-request correction smoke is recorded under
`results/appworld_rave_official_test_normal_90adc3f_sent_request_correction_v32/20260506_123327`
and reaches 3/3 success with 0 invalid tool calls and 0 unsafe state changes. Its
DeepSeek-chat intent-extraction companion under
`results/appworld_rave_official_test_normal_90adc3f_sent_request_correction_llm_intent_deepseek_v33/20260506_123342`
also reaches 3/3 with 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
changes.

The dedicated birthday child payment smoke is recorded under
`results/appworld_rave_official_test_normal_270f1ff_birthday_v26/20260506_121530`
and reaches 3/3 success with 0 invalid tool calls and 0 unsafe state changes. Its
DeepSeek-chat intent-extraction companion under
`results/appworld_rave_official_test_normal_270f1ff_birthday_llm_intent_deepseek_v27/20260506_121544`
also reaches 3/3 with 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
changes.

The dedicated 15-task Simple Note gap smoke is recorded under
`results/appworld_rave_official_test_normal_simple_note_gap15_smoke_v2/20260506_071635`
and reaches 15/15 success with 0 invalid tool calls and 0 unsafe state changes. The
DeepSeek-chat intent-extraction smoke for the bucket-list count family under
`results/appworld_rave_official_test_normal_simple_note_bucket_count_llm_intent_deepseek_chat_smoke/20260506_072157`
reaches 3/3 with 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state changes.

## Reproduction

```bash
TASK_IDS=$(head -120 appworld_020_root/data/datasets/test_normal.txt | tr '\n' ' ')
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python \
  experiments/run_appworld_rave_slice.py \
  --appworld-root <PROJECT_ROOT>/appworld_020_root \
  --output-root results/appworld_rave_official_test_normal_smoke120_0de03ea_offline_spotify_v57 \
  --experiment-name rave_official_test_normal_smoke120_0de03ea_offline_spotify_v57 \
  --task-ids $TASK_IDS \
  --agent deterministic \
  --timeout-seconds 120 \
  --flush-each-task
```
