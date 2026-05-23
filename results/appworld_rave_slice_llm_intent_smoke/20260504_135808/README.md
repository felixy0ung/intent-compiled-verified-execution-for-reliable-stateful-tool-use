# AppWorld RAVE Slice

This run evaluates a targeted public AppWorld stateful slice with typed RAVE intent compilers.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 3 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 1.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 18.3333 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 455.3333 |
| completion_tokens_per_task | 36.0 |
| token_proxy_per_task | 491.3333 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 37a8675_1 | appworld_venmo_send_to_phone_number | 1 | 3 | 0 | 1 |
| 771d8fc_1 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 1 |
