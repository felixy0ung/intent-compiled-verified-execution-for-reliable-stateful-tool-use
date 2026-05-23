# AppWorld RAVE Slice

This run evaluates a multi-attempt LLM AppWorld code-repair baseline on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_code_repair_slice |
| episodes | 12 |
| success_rate | 0.1667 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.75 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 18.5 |
| code_exec_calls_per_task | 2.25 |
| llm_calls_per_task | 2.25 |
| prompt_tokens_per_task | 4576.8333 |
| completion_tokens_per_task | 1050.5 |
| token_proxy_per_task | 5627.3333 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 0d8a4ee_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 13547f5_1 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_2 | appworld_llm_code_repair | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 37a8675_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 37a8675_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 024c982_3 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
