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
| invalid_tool_calls_per_task | 1.3333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 10.0 |
| code_exec_calls_per_task | 2.3333 |
| llm_calls_per_task | 3.6667 |
| prompt_tokens_per_task | 5030.0 |
| completion_tokens_per_task | 640.0 |
| token_proxy_per_task | 5670.0 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 13547f5_1 | appworld_llm_react_code | 1 | 2 | 0 | 4 |
| 37a8675_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
