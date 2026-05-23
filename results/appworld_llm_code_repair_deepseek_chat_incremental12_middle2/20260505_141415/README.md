# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 12 |
| success_rate | 0.5 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.8333 |
| unsafe_state_changes_per_task | 0.25 |
| api_calls_per_task | 28.0833 |
| code_exec_calls_per_task | 1.8333 |
| llm_calls_per_task | 1.8333 |
| prompt_tokens_per_task | 3376.1667 |
| completion_tokens_per_task | 663.0833 |
| token_proxy_per_task | 4039.25 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 09ac073_1 | appworld_llm_code_repair | 0 | 1 | 1 | 2 |
| 09ac073_2 | appworld_llm_code_repair | 0 | 1 | 1 | 2 |
| 09ac073_3 | appworld_llm_code_repair | 0 | 0 | 1 | 1 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 771d8fc_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_3 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| cf6abd2_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| cf6abd2_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| cf6abd2_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 07b42fd_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 07b42fd_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
