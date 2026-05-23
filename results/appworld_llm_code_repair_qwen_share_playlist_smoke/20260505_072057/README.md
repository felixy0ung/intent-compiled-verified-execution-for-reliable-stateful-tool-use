# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 3 |
| success_rate | 0.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 3.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 6.0 |
| code_exec_calls_per_task | 3.0 |
| llm_calls_per_task | 3.0 |
| prompt_tokens_per_task | 5658.0 |
| completion_tokens_per_task | 1365.0 |
| token_proxy_per_task | 7023.0 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 652485c_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 652485c_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 652485c_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
