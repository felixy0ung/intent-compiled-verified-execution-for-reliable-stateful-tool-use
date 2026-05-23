# AppWorld RAVE Slice

This run evaluates a typed-intent-only LLM AppWorld code ablation on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | appworld_llm_intent_code_slice |
| episodes | 3 |
| success_rate | 0.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 2.0 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 2.0 |
| prompt_tokens_per_task | 4406.6667 |
| completion_tokens_per_task | 362.0 |
| token_proxy_per_task | 4768.6667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 652485c_1 | appworld_llm_intent_code | 0 | 1 | 0 | 2 |
| 652485c_2 | appworld_llm_intent_code | 0 | 1 | 0 | 2 |
| 652485c_3 | appworld_llm_intent_code | 0 | 1 | 0 | 2 |
