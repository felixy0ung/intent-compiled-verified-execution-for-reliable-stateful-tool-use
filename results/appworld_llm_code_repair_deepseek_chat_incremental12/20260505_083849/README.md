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
| invalid_tool_calls_per_task | 1.75 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 73.6667 |
| code_exec_calls_per_task | 2.6667 |
| llm_calls_per_task | 2.6667 |
| prompt_tokens_per_task | 5807.1667 |
| completion_tokens_per_task | 1406.0833 |
| token_proxy_per_task | 7213.25 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 07bb666_1 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 07bb666_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 07bb666_3 | appworld_llm_code_repair | 0 | 0 | 0 | 1 |
| 396c5a2_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 396c5a2_2 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
| 396c5a2_3 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 57c3486_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 57c3486_2 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 57c3486_3 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 652485c_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 652485c_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 652485c_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
