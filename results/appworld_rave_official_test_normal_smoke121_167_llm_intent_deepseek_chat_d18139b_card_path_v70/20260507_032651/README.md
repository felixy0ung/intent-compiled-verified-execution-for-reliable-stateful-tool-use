# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 47 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 45.5957 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 11356.1702 |
| completion_tokens_per_task | 35.234 |
| token_proxy_per_task | 11391.4043 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 59fae45_1 | appworld_spotify_append_most_common_playlist_genre | 1 | 0 | 0 | 1 |
| 59fae45_2 | appworld_spotify_append_most_common_playlist_genre | 1 | 0 | 0 | 1 |
| 59fae45_3 | appworld_spotify_append_most_common_playlist_genre | 1 | 0 | 0 | 1 |
| b6d1104_1 | appworld_simple_note_update_monthly_venmo_expense | 1 | 0 | 0 | 1 |
| b6d1104_2 | appworld_simple_note_update_monthly_venmo_expense | 1 | 0 | 0 | 1 |
| b6d1104_3 | appworld_simple_note_update_monthly_venmo_expense | 1 | 0 | 0 | 1 |
| f861c32_1 | appworld_venmo_send_to_each_relationship_with_refill | 1 | 0 | 0 | 1 |
| f861c32_2 | appworld_venmo_send_to_each_relationship_with_refill | 1 | 0 | 0 | 1 |
| f861c32_3 | appworld_venmo_send_to_each_relationship_with_refill | 1 | 0 | 0 | 1 |
| 0a9d82a_1 | appworld_simple_note_longest_habit_streak | 1 | 0 | 0 | 1 |
| 0a9d82a_2 | appworld_simple_note_longest_habit_streak | 1 | 0 | 0 | 1 |
| 0a9d82a_3 | appworld_simple_note_longest_habit_streak | 1 | 0 | 0 | 1 |
| 166f4ff_1 | appworld_venmo_sum_recent_received_requests | 1 | 0 | 0 | 1 |
| 166f4ff_2 | appworld_venmo_sum_recent_received_requests | 1 | 0 | 0 | 1 |
| 166f4ff_3 | appworld_venmo_sum_recent_received_requests | 1 | 0 | 0 | 1 |
| 9016950_1 | appworld_venmo_signup_missing_relationship_accounts | 1 | 0 | 0 | 1 |
| 9016950_2 | appworld_venmo_signup_missing_relationship_accounts | 1 | 0 | 0 | 1 |
| 9016950_3 | appworld_venmo_signup_missing_relationship_accounts | 1 | 0 | 0 | 1 |
| dac78d9_1 | appworld_venmo_count_friends_since_month_start | 1 | 0 | 0 | 1 |
| dac78d9_2 | appworld_venmo_count_friends_since_month_start | 1 | 0 | 0 | 1 |
| dac78d9_3 | appworld_venmo_count_friends_since_month_start | 1 | 0 | 0 | 1 |
| f3f60f0_1 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 1 |
| f3f60f0_2 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 1 |
| f3f60f0_3 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 1 |
| ffe6d5e_1 | appworld_phone_reply_favorite_recipe_to_relationship | 1 | 0 | 0 | 1 |
| ffe6d5e_2 | appworld_phone_reply_favorite_recipe_to_relationship | 1 | 0 | 0 | 1 |
| ffe6d5e_3 | appworld_phone_reply_favorite_recipe_to_relationship | 1 | 0 | 0 | 1 |
| 8ce6779_1 | appworld_todoist_reassign_accepted_takeover_tasks | 1 | 0 | 0 | 1 |
| 8ce6779_2 | appworld_todoist_reassign_accepted_takeover_tasks | 1 | 0 | 0 | 1 |
| 8ce6779_3 | appworld_todoist_reassign_accepted_takeover_tasks | 1 | 0 | 0 | 1 |
| 83a7951_1 | appworld_splitwise_record_venmo_receipt_payments | 1 | 0 | 0 | 1 |
| 83a7951_2 | appworld_splitwise_record_venmo_receipt_payments | 1 | 0 | 0 | 1 |
| 83a7951_3 | appworld_splitwise_record_venmo_receipt_payments | 1 | 0 | 0 | 1 |
| 3aa1a22_1 | appworld_splitwise_accept_known_phone_invitations | 1 | 0 | 0 | 1 |
| 3aa1a22_2 | appworld_splitwise_accept_known_phone_invitations | 1 | 0 | 0 | 1 |
| 3aa1a22_3 | appworld_splitwise_accept_known_phone_invitations | 1 | 0 | 0 | 1 |
| 32616b5_1 | appworld_splitwise_record_trip_expenses_from_simple_note | 1 | 0 | 0 | 1 |
| 32616b5_2 | appworld_splitwise_record_trip_expenses_from_simple_note | 1 | 0 | 0 | 1 |
| 32616b5_3 | appworld_splitwise_record_trip_expenses_from_simple_note | 1 | 0 | 0 | 1 |
| 986aa4e_1 | appworld_spotify_apply_todoist_playlist_suggestions | 1 | 0 | 0 | 1 |
| 986aa4e_2 | appworld_spotify_apply_todoist_playlist_suggestions | 1 | 0 | 0 | 1 |
| 986aa4e_3 | appworld_spotify_apply_todoist_playlist_suggestions | 1 | 0 | 0 | 1 |
| 6b6ca61_1 | appworld_pay_csv_debts_via_venmo_or_splitwise | 1 | 0 | 0 | 1 |
| 6b6ca61_2 | appworld_pay_csv_debts_via_venmo_or_splitwise | 1 | 0 | 0 | 1 |
| 6b6ca61_3 | appworld_pay_csv_debts_via_venmo_or_splitwise | 1 | 0 | 0 | 1 |
| bde252e_1 | appworld_todoist_fill_today_from_schedule | 1 | 0 | 0 | 1 |
| bde252e_2 | appworld_todoist_fill_today_from_schedule | 1 | 0 | 0 | 1 |
