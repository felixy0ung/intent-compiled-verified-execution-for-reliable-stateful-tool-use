# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 6 |
| success_rate | 0.5 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.8333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 44.5 |
| code_exec_calls_per_task | 4.3333 |
| llm_calls_per_task | 4.3333 |
| prompt_tokens_per_task | 12064.3333 |
| completion_tokens_per_task | 1076.6667 |
| token_proxy_per_task | 13141.0 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 57c3486_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 57c3486_2 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 57c3486_3 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 652485c_1 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 652485c_2 | appworld_llm_react_code | 1 | 0 | 0 | 5 |
| 652485c_3 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
