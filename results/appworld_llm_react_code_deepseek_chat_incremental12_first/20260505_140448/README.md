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
| invalid_tool_calls_per_task | 0.75 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 13.8333 |
| code_exec_calls_per_task | 3.0833 |
| llm_calls_per_task | 4.0 |
| prompt_tokens_per_task | 10118.1667 |
| completion_tokens_per_task | 776.0833 |
| token_proxy_per_task | 10894.25 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 0d8a4ee_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 0d8a4ee_3 | appworld_llm_react_code | 1 | 1 | 0 | 5 |
| 13547f5_1 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 13547f5_2 | appworld_llm_react_code | 0 | 1 | 0 | 4 |
| 13547f5_3 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 37a8675_1 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 37a8675_2 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 37a8675_3 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 024c982_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 024c982_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 024c982_3 | appworld_llm_react_code | 1 | 2 | 0 | 4 |
