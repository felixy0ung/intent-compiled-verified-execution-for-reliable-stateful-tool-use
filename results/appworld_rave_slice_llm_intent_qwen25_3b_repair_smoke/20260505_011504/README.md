# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 6 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 26.1667 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 2350.3333 |
| completion_tokens_per_task | 33.6667 |
| token_proxy_per_task | 2384.0 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| aa8502b_1 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 1 |
| aa8502b_2 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 1 |
| aa8502b_3 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 1 |
| 692c77d_1 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 1 |
| 692c77d_2 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 1 |
| 692c77d_3 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 1 |
