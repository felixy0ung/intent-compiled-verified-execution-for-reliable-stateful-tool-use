# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 3 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 16.6667 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 10727.6667 |
| completion_tokens_per_task | 42.0 |
| token_proxy_per_task | 10769.6667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 90adc3f_1 | appworld_venmo_correct_sent_requests_yesterday_evening | 1 | 0 | 0 | 1 |
| 90adc3f_2 | appworld_venmo_correct_sent_requests_yesterday_evening | 1 | 0 | 0 | 1 |
| 90adc3f_3 | appworld_venmo_correct_sent_requests_yesterday_evening | 1 | 0 | 0 | 1 |
