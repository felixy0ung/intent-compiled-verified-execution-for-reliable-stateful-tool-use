# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 12 |
| success_rate | 0.25 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.3333 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 20.1667 |
| code_exec_calls_per_task | 2.25 |
| llm_calls_per_task | 2.25 |
| prompt_tokens_per_task | 4460.75 |
| completion_tokens_per_task | 896.4167 |
| token_proxy_per_task | 5357.1667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 4fab96f_1 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 4fab96f_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 4fab96f_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 6ea6792_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 6ea6792_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6ea6792_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| ff58e36_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| ff58e36_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| ff58e36_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 5e27cd7_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 5e27cd7_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
