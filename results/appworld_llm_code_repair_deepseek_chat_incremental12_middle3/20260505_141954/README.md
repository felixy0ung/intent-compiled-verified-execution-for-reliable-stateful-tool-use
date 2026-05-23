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
| invalid_tool_calls_per_task | 1.9167 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 56.25 |
| code_exec_calls_per_task | 2.6667 |
| llm_calls_per_task | 2.6667 |
| prompt_tokens_per_task | 5707.6667 |
| completion_tokens_per_task | 1330.1667 |
| token_proxy_per_task | 7037.8333 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| aa8502b_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| aa8502b_2 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| aa8502b_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| 6171bbc_1 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6171bbc_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 6171bbc_3 | appworld_llm_code_repair | 0 | 3 | 0 | 3 |
| f3f60f0_1 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| f3f60f0_2 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| f3f60f0_3 | appworld_llm_code_repair | 0 | 2 | 0 | 3 |
| 3ab5b8b_1 | appworld_llm_code_repair | 1 | 2 | 0 | 3 |
| 3ab5b8b_2 | appworld_llm_code_repair | 0 | 1 | 0 | 2 |
| 3ab5b8b_3 | appworld_llm_code_repair | 1 | 1 | 0 | 2 |
