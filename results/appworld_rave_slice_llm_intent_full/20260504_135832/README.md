# AppWorld RAVE Slice

This run evaluates a targeted public AppWorld stateful slice with typed RAVE intent compilers.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 12 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.4167 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 15.4167 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 455.1667 |
| completion_tokens_per_task | 34.75 |
| token_proxy_per_task | 489.9167 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 0d8a4ee_3 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 37a8675_1 | appworld_venmo_send_to_phone_number | 1 | 3 | 0 | 1 |
| 37a8675_2 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 1 |
| 37a8675_3 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 1 |
| 771d8fc_1 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 1 |
| 771d8fc_2 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 1 |
| 771d8fc_3 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 1 |
| cf6abd2_1 | appworld_bucket_list_status_update | 1 | 0 | 0 | 1 |
| cf6abd2_2 | appworld_bucket_list_status_update | 1 | 0 | 0 | 1 |
| cf6abd2_3 | appworld_bucket_list_status_update | 1 | 0 | 0 | 1 |
