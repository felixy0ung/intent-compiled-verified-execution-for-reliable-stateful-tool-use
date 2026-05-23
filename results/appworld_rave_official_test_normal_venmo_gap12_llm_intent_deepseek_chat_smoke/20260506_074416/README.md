# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 12 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.5 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 16.4167 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 10129.5 |
| completion_tokens_per_task | 36.25 |
| token_proxy_per_task | 10165.75 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 2c544f9_1 | appworld_venmo_send_to_named_user | 1 | 2 | 0 | 1 |
| 2c544f9_2 | appworld_venmo_send_to_named_user | 1 | 2 | 0 | 1 |
| 2c544f9_3 | appworld_venmo_send_to_named_user | 1 | 2 | 0 | 1 |
| 9ef798c_1 | appworld_venmo_accept_named_carpool_request_this_month | 1 | 0 | 0 | 1 |
| 9ef798c_2 | appworld_venmo_accept_named_carpool_request_this_month | 1 | 0 | 0 | 1 |
| 9ef798c_3 | appworld_venmo_accept_named_carpool_request_this_month | 1 | 0 | 0 | 1 |
| 9dabbc9_1 | appworld_venmo_correct_housing_bill_request | 1 | 0 | 0 | 1 |
| 9dabbc9_2 | appworld_venmo_correct_housing_bill_request | 1 | 0 | 0 | 1 |
| 9dabbc9_3 | appworld_venmo_correct_housing_bill_request | 1 | 0 | 0 | 1 |
| ccf4b82_1 | appworld_venmo_approve_requests_and_withdraw_balance | 1 | 0 | 0 | 1 |
| ccf4b82_2 | appworld_venmo_approve_requests_and_withdraw_balance | 1 | 0 | 0 | 1 |
| ccf4b82_3 | appworld_venmo_approve_requests_and_withdraw_balance | 1 | 0 | 0 | 1 |
