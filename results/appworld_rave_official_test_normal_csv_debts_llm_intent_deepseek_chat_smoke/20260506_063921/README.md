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
| api_calls_per_task | 101.0 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 8931.0 |
| completion_tokens_per_task | 38.3333 |
| token_proxy_per_task | 8969.3333 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 6b6ca61_1 | appworld_pay_csv_debts_via_venmo_or_splitwise | 1 | 0 | 0 | 1 |
| 6b6ca61_2 | appworld_pay_csv_debts_via_venmo_or_splitwise | 1 | 0 | 0 | 1 |
| 6b6ca61_3 | appworld_pay_csv_debts_via_venmo_or_splitwise | 1 | 0 | 0 | 1 |
