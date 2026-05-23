# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 30 |
| success_rate | 0.3333 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.8 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 16.7 |
| code_exec_calls_per_task | 3.1667 |
| llm_calls_per_task | 3.6667 |
| prompt_tokens_per_task | 6663.5 |
| completion_tokens_per_task | 806.5 |
| token_proxy_per_task | 7470.0 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 0d8a4ee_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 0d8a4ee_3 | appworld_llm_react_code | 0 | 0 | 0 | 3 |
| 13547f5_1 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 13547f5_2 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 13547f5_3 | appworld_llm_react_code | 1 | 1 | 0 | 4 |
| 37a8675_1 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 37a8675_2 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 37a8675_3 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 4fab96f_1 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| 4fab96f_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 4fab96f_3 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| 6ea6792_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 6ea6792_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 6ea6792_3 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 5e27cd7_1 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 5e27cd7_2 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 5e27cd7_3 | appworld_llm_react_code | 0 | 1 | 0 | 4 |
| 771d8fc_1 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 771d8fc_2 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 771d8fc_3 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| cf6abd2_1 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| cf6abd2_2 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| cf6abd2_3 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 07b42fd_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 07b42fd_2 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 07b42fd_3 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| aa8502b_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| aa8502b_2 | appworld_llm_react_code | 0 | 4 | 0 | 5 |
| aa8502b_3 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
