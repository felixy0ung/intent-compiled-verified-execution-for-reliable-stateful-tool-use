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
| api_calls_per_task | 67.6667 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 9102.6667 |
| completion_tokens_per_task | 29.3333 |
| token_proxy_per_task | 9132.0 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| bde252e_1 | appworld_todoist_fill_today_from_schedule | 1 | 0 | 0 | 1 |
| bde252e_2 | appworld_todoist_fill_today_from_schedule | 1 | 0 | 0 | 1 |
| bde252e_3 | appworld_todoist_fill_today_from_schedule | 1 | 0 | 0 | 1 |
