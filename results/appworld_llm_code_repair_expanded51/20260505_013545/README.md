# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 51 |
| success_rate | 0.3922 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.4902 |
| unsafe_state_changes_per_task | 0.0588 |
| api_calls_per_task | 71.3922 |
| code_exec_calls_per_task | 2.3137 |
| llm_calls_per_task | 2.3137 |
| prompt_tokens_per_task | 4171.9804 |
| completion_tokens_per_task | 1008.6275 |
| token_proxy_per_task | 5180.6078 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 0d8a4ee_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 13547f5_1 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_2 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_1 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 024c982_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 024c982_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 4fab96f_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 4fab96f_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 4fab96f_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6ea6792_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6ea6792_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6ea6792_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| ff58e36_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| ff58e36_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| ff58e36_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 5e27cd7_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 09ac073_1 | appworld_llm_code_repair | 0 | 2 | 1 | 3 |
| 09ac073_2 | appworld_llm_code_repair | 0 | 1 | 1 | 2 |
| 09ac073_3 | appworld_llm_code_repair | 0 | 2 | 1 | 3 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| cf6abd2_2 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| cf6abd2_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 07b42fd_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| aa8502b_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| aa8502b_2 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| aa8502b_3 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 6171bbc_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6171bbc_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6171bbc_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| f3f60f0_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| f3f60f0_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| f3f60f0_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 3ab5b8b_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 3ab5b8b_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 3ab5b8b_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 692c77d_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 692c77d_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 692c77d_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
