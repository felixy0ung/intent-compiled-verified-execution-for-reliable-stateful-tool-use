# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 6 |
| success_rate | 0.5 |
| supported_rate | 0.5 |
| invalid_tool_calls_per_task | 0.5 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 10.0 |
| code_exec_calls_per_task | 0.5 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 10870.8333 |
| completion_tokens_per_task | 36.8333 |
| token_proxy_per_task | 10907.6667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 3b8fb7a_1 | unsupported | 0 | 1 | 0 | 1 |
| 3b8fb7a_2 | unsupported | 0 | 1 | 0 | 1 |
| 3b8fb7a_3 | unsupported | 0 | 1 | 0 | 1 |
| b9c5c9a_1 | appworld_file_update_reunion_rsvps_from_phone | 1 | 0 | 0 | 1 |
| b9c5c9a_2 | appworld_file_update_reunion_rsvps_from_phone | 1 | 0 | 0 | 1 |
| b9c5c9a_3 | appworld_file_update_reunion_rsvps_from_phone | 1 | 0 | 0 | 1 |
