# AppWorld RAVE Slice

This run evaluates a targeted public AppWorld stateful slice with typed RAVE intent compilers.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_slice |
| episodes | 4 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.75 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 15.75 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 0.0 |
| token_proxy_per_task | 190.25 |

## Episodes

| task_id | intent_type | success | invalid | unsafe |
| --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 |
| 37a8675_1 | appworld_venmo_send_to_phone_number | 1 | 3 | 0 |
| 771d8fc_1 | appworld_delete_phone_spam_messages | 1 | 0 | 0 |
| cf6abd2_1 | appworld_bucket_list_status_update | 1 | 0 | 0 |
