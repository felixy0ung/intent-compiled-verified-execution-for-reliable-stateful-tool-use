# AppWorld RAVE Slice

This run evaluates a targeted public AppWorld stateful slice with typed RAVE intent compilers.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_slice |
| episodes | 3 |
| success_rate | 0.6667 |
| supported_rate | 0.6667 |
| invalid_tool_calls_per_task | 0.3333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 5.6667 |
| code_exec_calls_per_task | 0.6667 |
| llm_calls_per_task | 0.0 |
| prompt_tokens_per_task | 0.0 |
| completion_tokens_per_task | 0.0 |
| token_proxy_per_task | 183.6667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0de03ea_1 | appworld_spotify_play_offline_downloaded_collection | 1 | 0 | 0 | 0 |
| 0de03ea_2 | unsupported | 0 | 1 | 0 | 0 |
| 0de03ea_3 | appworld_spotify_play_offline_downloaded_collection | 1 | 0 | 0 | 0 |
