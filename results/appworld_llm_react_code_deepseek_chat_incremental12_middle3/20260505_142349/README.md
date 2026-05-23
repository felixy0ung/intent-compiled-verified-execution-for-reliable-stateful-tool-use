# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 12 |
| success_rate | 0.25 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 2.1667 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 36.9167 |
| code_exec_calls_per_task | 3.0833 |
| llm_calls_per_task | 4.5 |
| prompt_tokens_per_task | 11701.75 |
| completion_tokens_per_task | 1291.0833 |
| token_proxy_per_task | 12992.8333 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| aa8502b_1 | appworld_llm_react_code | 0 | 4 | 0 | 5 |
| aa8502b_2 | appworld_llm_react_code | 1 | 2 | 0 | 5 |
| aa8502b_3 | appworld_llm_react_code | 0 | 4 | 0 | 5 |
| 6171bbc_1 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 6171bbc_2 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 6171bbc_3 | appworld_llm_react_code | 1 | 2 | 0 | 5 |
| f3f60f0_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| f3f60f0_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| f3f60f0_3 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 3ab5b8b_1 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 3ab5b8b_2 | appworld_llm_react_code | 0 | 1 | 0 | 3 |
| 3ab5b8b_3 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
