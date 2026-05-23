# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 3 |
| success_rate | 0.3333 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 21.3333 |
| code_exec_calls_per_task | 5.0 |
| llm_calls_per_task | 5.0 |
| prompt_tokens_per_task | 14818.3333 |
| completion_tokens_per_task | 1037.3333 |
| token_proxy_per_task | 15855.6667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 652485c_1 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 652485c_2 | appworld_llm_react_code | 1 | 0 | 0 | 5 |
| 652485c_3 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
