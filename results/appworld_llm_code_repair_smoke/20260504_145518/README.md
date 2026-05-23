# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 4 |
| success_rate | 0.25 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.75 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 281.75 |
| code_exec_calls_per_task | 2.5 |
| llm_calls_per_task | 2.5 |
| prompt_tokens_per_task | 2920.75 |
| completion_tokens_per_task | 1451.5 |
| token_proxy_per_task | 4372.25 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 771d8fc_1 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| cf6abd2_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
