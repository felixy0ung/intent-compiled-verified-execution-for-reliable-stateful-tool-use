# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 39 |
| success_rate | 0.4359 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.5641 |
| unsafe_state_changes_per_task | 0.0769 |
| api_calls_per_task | 126.4872 |
| code_exec_calls_per_task | 2.3333 |
| llm_calls_per_task | 2.3333 |
| prompt_tokens_per_task | 3556.7949 |
| completion_tokens_per_task | 912.7692 |
| token_proxy_per_task | 4469.5641 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 0d8a4ee_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 0d8a4ee_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 13547f5_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 13547f5_2 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 37a8675_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 024c982_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_3 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 4fab96f_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 4fab96f_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 4fab96f_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6ea6792_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6ea6792_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6ea6792_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 5e27cd7_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 09ac073_1 | appworld_llm_code_repair | 0 | 0 | 1 | 1 |
| 09ac073_2 | appworld_llm_code_repair | 0 | 2 | 1 | 3 |
| 09ac073_3 | appworld_llm_code_repair | 0 | 0 | 1 | 1 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| cf6abd2_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| cf6abd2_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 07b42fd_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| aa8502b_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| aa8502b_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| aa8502b_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 6171bbc_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6171bbc_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6171bbc_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
