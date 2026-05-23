# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 15 |
| success_rate | 0.6 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.3333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 85.1333 |
| code_exec_calls_per_task | 2.2667 |
| llm_calls_per_task | 2.2667 |
| prompt_tokens_per_task | 2240.0667 |
| completion_tokens_per_task | 912.3333 |
| token_proxy_per_task | 3152.4 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 0d8a4ee_2 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 0d8a4ee_3 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 37a8675_2 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 37a8675_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_2 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| cf6abd2_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 07b42fd_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 07b42fd_2 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 07b42fd_3 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
