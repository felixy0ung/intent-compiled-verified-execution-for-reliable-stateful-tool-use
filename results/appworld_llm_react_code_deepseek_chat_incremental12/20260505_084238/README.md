# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 12 |
| success_rate | 0.4167 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.75 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 29.9167 |
| code_exec_calls_per_task | 3.9167 |
| llm_calls_per_task | 4.1667 |
| prompt_tokens_per_task | 11079.3333 |
| completion_tokens_per_task | 868.1667 |
| token_proxy_per_task | 11947.5 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 07bb666_1 | appworld_llm_react_code | 0 | 0 | 0 | 3 |
| 07bb666_2 | appworld_llm_react_code | 0 | 1 | 0 | 4 |
| 07bb666_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 396c5a2_1 | appworld_llm_react_code | 1 | 0 | 0 | 3 |
| 396c5a2_2 | appworld_llm_react_code | 1 | 2 | 0 | 5 |
| 396c5a2_3 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 57c3486_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 57c3486_2 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 57c3486_3 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 652485c_1 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 652485c_2 | appworld_llm_react_code | 1 | 0 | 0 | 5 |
| 652485c_3 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
