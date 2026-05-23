# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 12 |
| success_rate | 0.3333 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.3333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 19.1667 |
| code_exec_calls_per_task | 3.4167 |
| llm_calls_per_task | 4.5 |
| prompt_tokens_per_task | 11616.1667 |
| completion_tokens_per_task | 1026.4167 |
| token_proxy_per_task | 12642.5833 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 4fab96f_1 | appworld_llm_react_code | 1 | 1 | 0 | 5 |
| 4fab96f_2 | appworld_llm_react_code | 1 | 1 | 0 | 5 |
| 4fab96f_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 6ea6792_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 6ea6792_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 6ea6792_3 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| ff58e36_1 | appworld_llm_react_code | 0 | 0 | 0 | 3 |
| ff58e36_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| ff58e36_3 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 5e27cd7_1 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 5e27cd7_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 5e27cd7_3 | appworld_llm_react_code | 1 | 2 | 0 | 4 |
