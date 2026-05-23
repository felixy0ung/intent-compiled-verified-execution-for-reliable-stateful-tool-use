# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 6 |
| success_rate | 0.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 2.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 1.5 |
| code_exec_calls_per_task | 2.5 |
| llm_calls_per_task | 2.5 |
| prompt_tokens_per_task | 4122.8333 |
| completion_tokens_per_task | 720.3333 |
| token_proxy_per_task | 4843.1667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| d4e9306_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| d4e9306_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| d4e9306_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| b7a9ee9_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| b7a9ee9_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| b7a9ee9_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
