# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 3 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 258.6667 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 10210.3333 |
| completion_tokens_per_task | 33.3333 |
| token_proxy_per_task | 10243.6667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| d194965_1 | appworld_spotify_playlist_from_recent_simple_note | 1 | 0 | 0 | 1 |
| d194965_2 | appworld_spotify_playlist_from_recent_simple_note | 1 | 0 | 0 | 1 |
| d194965_3 | appworld_spotify_playlist_from_recent_simple_note | 1 | 0 | 0 | 1 |
