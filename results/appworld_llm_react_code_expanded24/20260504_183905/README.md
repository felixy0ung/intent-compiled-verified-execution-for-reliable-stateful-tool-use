# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 24 |
| success_rate | 0.4583 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.9167 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 17.0 |
| code_exec_calls_per_task | 3.375 |
| llm_calls_per_task | 3.8333 |
| prompt_tokens_per_task | 6645.75 |
| completion_tokens_per_task | 895.7917 |
| token_proxy_per_task | 7541.5417 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_react_code | 0 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| 0d8a4ee_3 | appworld_llm_react_code | 1 | 3 | 0 | 5 |
| 13547f5_1 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 13547f5_2 | appworld_llm_react_code | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 37a8675_1 | appworld_llm_react_code | 0 | 1 | 0 | 3 |
| 37a8675_2 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 37a8675_3 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 4fab96f_1 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 4fab96f_2 | appworld_llm_react_code | 1 | 0 | 0 | 5 |
| 4fab96f_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 771d8fc_1 | appworld_llm_react_code | 0 | 1 | 0 | 3 |
| 771d8fc_2 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 771d8fc_3 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| cf6abd2_1 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| cf6abd2_2 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| cf6abd2_3 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| 07b42fd_1 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 07b42fd_2 | appworld_llm_react_code | 0 | 4 | 0 | 5 |
| 07b42fd_3 | appworld_llm_react_code | 1 | 3 | 0 | 5 |
| aa8502b_1 | appworld_llm_react_code | 1 | 2 | 0 | 5 |
| aa8502b_2 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| aa8502b_3 | appworld_llm_react_code | 1 | 2 | 0 | 5 |
