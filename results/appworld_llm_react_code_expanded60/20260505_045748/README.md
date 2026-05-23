# AppWorld RAVE Slice

This run evaluates a multi-step LLM AppWorld code-observation baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_react_code_slice |
| episodes | 60 |
| success_rate | 0.2333 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.4333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 19.0833 |
| code_exec_calls_per_task | 3.2667 |
| llm_calls_per_task | 4.4333 |
| prompt_tokens_per_task | 10642.4833 |
| completion_tokens_per_task | 931.4333 |
| token_proxy_per_task | 11573.9167 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 0d8a4ee_2 | appworld_llm_react_code | 1 | 0 | 0 | 4 |
| 0d8a4ee_3 | appworld_llm_react_code | 0 | 4 | 0 | 5 |
| 13547f5_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 13547f5_2 | appworld_llm_react_code | 0 | 0 | 0 | 3 |
| 13547f5_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 37a8675_1 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 37a8675_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 37a8675_3 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 024c982_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 024c982_2 | appworld_llm_react_code | 1 | 2 | 0 | 4 |
| 024c982_3 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 4fab96f_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 4fab96f_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 4fab96f_3 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 6ea6792_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 6ea6792_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 6ea6792_3 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| ff58e36_1 | appworld_llm_react_code | 1 | 3 | 0 | 5 |
| ff58e36_2 | appworld_llm_react_code | 1 | 2 | 0 | 4 |
| ff58e36_3 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 5e27cd7_1 | appworld_llm_react_code | 1 | 0 | 0 | 3 |
| 5e27cd7_2 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 5e27cd7_3 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 09ac073_1 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 09ac073_2 | appworld_llm_react_code | 1 | 0 | 0 | 2 |
| 09ac073_3 | appworld_llm_react_code | 0 | 2 | 0 | 4 |
| 771d8fc_1 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 771d8fc_2 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| 771d8fc_3 | appworld_llm_react_code | 0 | 0 | 0 | 2 |
| cf6abd2_1 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| cf6abd2_2 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| cf6abd2_3 | appworld_llm_react_code | 0 | 0 | 0 | 4 |
| 07b42fd_1 | appworld_llm_react_code | 1 | 2 | 0 | 4 |
| 07b42fd_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 07b42fd_3 | appworld_llm_react_code | 1 | 1 | 0 | 3 |
| aa8502b_1 | appworld_llm_react_code | 1 | 3 | 0 | 5 |
| aa8502b_2 | appworld_llm_react_code | 0 | 4 | 0 | 5 |
| aa8502b_3 | appworld_llm_react_code | 1 | 3 | 0 | 5 |
| 6171bbc_1 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 6171bbc_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 6171bbc_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| f3f60f0_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| f3f60f0_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| f3f60f0_3 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 3ab5b8b_1 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 3ab5b8b_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 3ab5b8b_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 692c77d_1 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 692c77d_2 | appworld_llm_react_code | 0 | 2 | 0 | 5 |
| 692c77d_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 31dc501_1 | appworld_llm_react_code | 0 | 0 | 0 | 5 |
| 31dc501_2 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 31dc501_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 07bb666_1 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 07bb666_2 | appworld_llm_react_code | 0 | 1 | 0 | 4 |
| 07bb666_3 | appworld_llm_react_code | 0 | 1 | 0 | 5 |
| 396c5a2_1 | appworld_llm_react_code | 1 | 1 | 0 | 4 |
| 396c5a2_2 | appworld_llm_react_code | 0 | 3 | 0 | 5 |
| 396c5a2_3 | appworld_llm_react_code | 1 | 0 | 0 | 3 |
