# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 63 |
| success_rate | 0.3016 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.5714 |
| unsafe_state_changes_per_task | 0.0476 |
| api_calls_per_task | 42.6032 |
| code_exec_calls_per_task | 2.3175 |
| llm_calls_per_task | 2.3175 |
| prompt_tokens_per_task | 4630.5238 |
| completion_tokens_per_task | 943.9048 |
| token_proxy_per_task | 5574.4286 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 0d8a4ee_3 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 13547f5_1 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_2 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 37a8675_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 024c982_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 4fab96f_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 4fab96f_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 4fab96f_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6ea6792_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6ea6792_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6ea6792_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| ff58e36_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| ff58e36_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| ff58e36_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 5e27cd7_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 09ac073_1 | appworld_llm_code_repair | 0 | 1 | 1 | 2 |
| 09ac073_2 | appworld_llm_code_repair | 0 | 1 | 1 | 2 |
| 09ac073_3 | appworld_llm_code_repair | 0 | 0 | 1 | 1 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_3 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| cf6abd2_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| cf6abd2_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| cf6abd2_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 07b42fd_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| aa8502b_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| aa8502b_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| aa8502b_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6171bbc_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6171bbc_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6171bbc_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| f3f60f0_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| f3f60f0_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| f3f60f0_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 3ab5b8b_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 3ab5b8b_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 3ab5b8b_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 692c77d_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 692c77d_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 692c77d_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 31dc501_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 31dc501_2 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 31dc501_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 07bb666_1 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 07bb666_2 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 07bb666_3 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 396c5a2_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 396c5a2_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 396c5a2_3 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 57c3486_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 57c3486_2 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 57c3486_3 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
