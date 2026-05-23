# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 10 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 41.6 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 3914.4 |
| completion_tokens_per_task | 32.2 |
| token_proxy_per_task | 3946.6 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 50e1ac9_1 | appworld_spotify_top_played_genre_titles | 1 | 0 | 0 | 1 |
| 50e1ac9_2 | appworld_spotify_top_played_genre_titles | 1 | 0 | 0 | 1 |
| 50e1ac9_3 | appworld_spotify_top_played_genre_titles | 1 | 0 | 0 | 1 |
| fac291d_1 | appworld_spotify_count_unique_library_songs | 1 | 0 | 0 | 1 |
| fac291d_2 | appworld_spotify_count_unique_library_songs | 1 | 0 | 0 | 1 |
| fac291d_3 | appworld_spotify_count_unique_library_songs | 1 | 0 | 0 | 1 |
| 530b157_1 | appworld_venmo_pay_grocery_from_text_and_notify | 1 | 0 | 0 | 1 |
| 530b157_2 | appworld_venmo_pay_grocery_from_text_and_notify | 1 | 0 | 0 | 1 |
| 530b157_3 | appworld_venmo_pay_grocery_from_text_and_notify | 1 | 0 | 0 | 1 |
| 4ec8de5_1 | appworld_spotify_count_recent_release_library_songs | 1 | 0 | 0 | 1 |
