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
| api_calls_per_task | 22.0 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 11319.0 |
| completion_tokens_per_task | 27.0 |
| token_proxy_per_task | 11346.0 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| d18139b_1 | appworld_venmo_approve_roommate_requests_this_month | 1 | 0 | 0 | 1 |
| d18139b_2 | appworld_venmo_approve_roommate_requests_this_month | 1 | 0 | 0 | 1 |
| d18139b_3 | appworld_venmo_approve_roommate_requests_this_month | 1 | 0 | 0 | 1 |
