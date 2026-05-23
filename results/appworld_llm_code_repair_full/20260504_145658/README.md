# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 12 |
| success_rate | 0.4167 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.0833 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 18.4167 |
| code_exec_calls_per_task | 2.0 |
| llm_calls_per_task | 2.0 |
| prompt_tokens_per_task | 1777.25 |
| completion_tokens_per_task | 918.25 |
| token_proxy_per_task | 2695.5 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 0d8a4ee_2 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 0d8a4ee_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 37a8675_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 771d8fc_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| cf6abd2_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
