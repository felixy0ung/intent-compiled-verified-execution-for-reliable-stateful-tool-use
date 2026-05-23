# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 21 |
| success_rate | 0.4286 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.8095 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 14.7619 |
| code_exec_calls_per_task | 2.7619 |
| llm_calls_per_task | 3.4762 |
| prompt_tokens_per_task | 5120.8095 |
| completion_tokens_per_task | 788.8571 |
| token_proxy_per_task | 5909.6667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_react_code | 0 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| 0d8a4ee_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 13547f5_1 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 13547f5_2 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 13547f5_3 | appworld_llm_react_code | 1 | 0 | 0 | 5 |
| 37a8675_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 37a8675_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 37a8675_3 | appworld_llm_react_code | 0 | 0 | 0 | 1 |
| 771d8fc_1 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 771d8fc_2 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 771d8fc_3 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| cf6abd2_1 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| cf6abd2_2 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| cf6abd2_3 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 07b42fd_1 | appworld_llm_react_code | 1 | 1 | 0 | 4 |
| 07b42fd_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 07b42fd_3 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| aa8502b_1 | appworld_llm_react_code | 1 | 2 | 0 | 4 |
| aa8502b_2 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| aa8502b_3 | appworld_llm_react_code | 0 | 4 | 0 | 5 |
