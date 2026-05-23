# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 6 |
| success_rate | 0.3333 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.8333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 60.0 |
| code_exec_calls_per_task | 3.3333 |
| llm_calls_per_task | 4.8333 |
| prompt_tokens_per_task | 13514.3333 |
| completion_tokens_per_task | 1467.5 |
| token_proxy_per_task | 14981.8333 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| d4e9306_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| d4e9306_2 | appworld_llm_react_code | 1 | 3 | 0 | 5 |
| d4e9306_3 | appworld_llm_react_code | 1 | 3 | 0 | 5 |
| b7a9ee9_1 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| b7a9ee9_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| b7a9ee9_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
