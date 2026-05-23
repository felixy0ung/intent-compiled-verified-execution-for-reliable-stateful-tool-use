# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 24 |
| success_rate | 0.5 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.2083 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 99.2917 |
| code_exec_calls_per_task | 2.0 |
| llm_calls_per_task | 2.0 |
| prompt_tokens_per_task | 2200.125 |
| completion_tokens_per_task | 841.0417 |
| token_proxy_per_task | 3041.1667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 0d8a4ee_3 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 13547f5_1 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_2 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 37a8675_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 4fab96f_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 4fab96f_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 4fab96f_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| cf6abd2_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_3 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 07b42fd_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| aa8502b_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| aa8502b_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| aa8502b_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
