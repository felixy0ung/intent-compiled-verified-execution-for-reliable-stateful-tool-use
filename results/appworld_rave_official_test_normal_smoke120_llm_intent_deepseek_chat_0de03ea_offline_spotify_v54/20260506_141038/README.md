# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 120 |
| success_rate | 0.9667 |
| supported_rate | 0.975 |
| invalid_tool_calls_per_task | 0.075 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 35.575 |
| code_exec_calls_per_task | 0.975 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 11336.2083 |
| completion_tokens_per_task | 34.225 |
| token_proxy_per_task | 11370.4333 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 3d9a636_1 | appworld_venmo_reset_friends_to_phone_friends | 1 | 0 | 0 | 1 |
| 3d9a636_2 | appworld_venmo_reset_friends_to_phone_friends | 1 | 0 | 0 | 1 |
| 3d9a636_3 | appworld_venmo_reset_friends_to_phone_friends | 1 | 0 | 0 | 1 |
| fd1f8fa_1 | appworld_spotify_filter_queue_by_liked_status | 1 | 0 | 0 | 1 |
| fd1f8fa_2 | appworld_spotify_filter_queue_by_liked_status | 1 | 0 | 0 | 1 |
| fd1f8fa_3 | appworld_spotify_filter_queue_by_liked_status | 1 | 0 | 0 | 1 |
| 325d6ec_1 | appworld_spotify_navigate_until_private_status | 1 | 0 | 0 | 1 |
| 325d6ec_2 | appworld_spotify_navigate_until_private_status | 1 | 0 | 0 | 1 |
| 325d6ec_3 | appworld_spotify_navigate_until_private_status | 1 | 0 | 0 | 1 |
| 29a7b7e_1 | appworld_file_reorganize_dated_meeting_files | 1 | 0 | 0 | 1 |
| 29a7b7e_2 | appworld_file_reorganize_dated_meeting_files | 1 | 0 | 0 | 1 |
| 29a7b7e_3 | appworld_file_reorganize_dated_meeting_files | 1 | 0 | 0 | 1 |
| 21abae1_1 | appworld_venmo_sum_month_transactions | 1 | 0 | 0 | 1 |
| 21abae1_2 | appworld_venmo_sum_month_transactions | 1 | 0 | 0 | 1 |
| 21abae1_3 | appworld_venmo_sum_month_transactions | 1 | 0 | 0 | 1 |
| 634f342_1 | appworld_spotify_archive_playlist_songs_from_file | 1 | 0 | 0 | 1 |
| 634f342_2 | appworld_spotify_archive_playlist_songs_from_file | 1 | 0 | 0 | 1 |
| 634f342_3 | appworld_spotify_archive_playlist_songs_from_file | 1 | 0 | 0 | 1 |
| 8749218_1 | appworld_spotify_reset_queue_with_recommendations | 1 | 0 | 0 | 1 |
| 8749218_2 | appworld_spotify_reset_queue_with_recommendations | 1 | 0 | 0 | 1 |
| 8749218_3 | appworld_spotify_reset_queue_with_recommendations | 1 | 0 | 0 | 1 |
| 2d9f728_1 | appworld_venmo_settle_roommate_dinner | 1 | 0 | 0 | 1 |
| 2d9f728_2 | appworld_venmo_settle_roommate_dinner | 1 | 0 | 0 | 1 |
| 2d9f728_3 | appworld_venmo_settle_roommate_dinner | 1 | 0 | 0 | 1 |
| 6f4b9a5_1 | appworld_simple_note_fill_liked_song_release_months | 1 | 0 | 0 | 1 |
| 6f4b9a5_2 | appworld_simple_note_fill_liked_song_release_months | 1 | 0 | 0 | 1 |
| 6f4b9a5_3 | appworld_simple_note_fill_liked_song_release_months | 1 | 0 | 0 | 1 |
| d6ac34d_1 | appworld_simple_note_add_today_habit_log | 1 | 0 | 0 | 1 |
| d6ac34d_2 | appworld_simple_note_add_today_habit_log | 1 | 0 | 0 | 1 |
| d6ac34d_3 | appworld_simple_note_add_today_habit_log | 1 | 0 | 0 | 1 |
| 0d01c76_1 | appworld_simple_note_import_markdown_files | 1 | 0 | 0 | 1 |
| 0d01c76_2 | appworld_simple_note_import_markdown_files | 1 | 0 | 0 | 1 |
| 0d01c76_3 | appworld_simple_note_import_markdown_files | 1 | 0 | 0 | 1 |
| ff58e36_1 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 1 |
| ff58e36_2 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 1 |
| ff58e36_3 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 1 |
| d18139b_1 | appworld_venmo_approve_roommate_requests_this_month | 1 | 0 | 0 | 1 |
| d18139b_2 | appworld_venmo_approve_roommate_requests_this_month | 0 | 0 | 0 | 1 |
| d18139b_3 | appworld_venmo_approve_roommate_requests_this_month | 1 | 0 | 0 | 1 |
| 5a83b05_1 | appworld_file_delete_downloads_by_extension | 1 | 0 | 0 | 1 |
| 5a83b05_2 | appworld_file_delete_downloads_by_extension | 1 | 0 | 0 | 1 |
| 5a83b05_3 | appworld_file_delete_downloads_by_extension | 1 | 0 | 0 | 1 |
| 042a9fc_1 | appworld_spotify_apply_phone_playlist_suggestions | 1 | 0 | 0 | 1 |
| 042a9fc_2 | appworld_spotify_apply_phone_playlist_suggestions | 1 | 0 | 0 | 1 |
| 042a9fc_3 | appworld_spotify_apply_phone_playlist_suggestions | 1 | 0 | 0 | 1 |
| cef9191_1 | appworld_spotify_followed_artist_follower_extreme | 1 | 0 | 0 | 1 |
| cef9191_2 | appworld_spotify_followed_artist_follower_extreme | 1 | 0 | 0 | 1 |
| cef9191_3 | appworld_spotify_followed_artist_follower_extreme | 1 | 0 | 0 | 1 |
| 3b8fb7a_1 | unsupported | 0 | 1 | 0 | 1 |
| 3b8fb7a_2 | unsupported | 0 | 1 | 0 | 1 |
| 3b8fb7a_3 | unsupported | 0 | 1 | 0 | 1 |
| afc4005_1 | appworld_simple_note_workout_duration | 1 | 0 | 0 | 1 |
| afc4005_2 | appworld_simple_note_workout_duration | 1 | 0 | 0 | 1 |
| afc4005_3 | appworld_simple_note_workout_duration | 1 | 0 | 0 | 1 |
| 9dabbc9_1 | appworld_venmo_correct_housing_bill_request | 1 | 0 | 0 | 1 |
| 9dabbc9_2 | appworld_venmo_correct_housing_bill_request | 1 | 0 | 0 | 1 |
| 9dabbc9_3 | appworld_venmo_correct_housing_bill_request | 1 | 0 | 0 | 1 |
| 425a494_1 | appworld_spotify_liked_genre_extreme | 1 | 0 | 0 | 1 |
| 425a494_2 | appworld_spotify_liked_genre_extreme | 1 | 0 | 0 | 1 |
| 425a494_3 | appworld_spotify_liked_genre_extreme | 1 | 0 | 0 | 1 |
| a30375d_1 | appworld_simple_note_random_quote | 1 | 0 | 0 | 1 |
| a30375d_2 | appworld_simple_note_random_quote | 1 | 0 | 0 | 1 |
| a30375d_3 | appworld_simple_note_random_quote | 1 | 0 | 0 | 1 |
| 09b0ee6_1 | appworld_spotify_playlist_artist_song_count_extreme | 1 | 0 | 0 | 1 |
| 09b0ee6_2 | appworld_spotify_playlist_artist_song_count_extreme | 1 | 0 | 0 | 1 |
| 09b0ee6_3 | appworld_spotify_playlist_artist_song_count_extreme | 1 | 0 | 0 | 1 |
| d194965_1 | appworld_spotify_playlist_from_recent_simple_note | 1 | 0 | 0 | 1 |
| d194965_2 | appworld_spotify_playlist_from_recent_simple_note | 1 | 0 | 0 | 1 |
| d194965_3 | appworld_spotify_playlist_from_recent_simple_note | 1 | 0 | 0 | 1 |
| 7847649_1 | appworld_simple_note_count_bucket_list_status | 1 | 0 | 0 | 1 |
| 7847649_2 | appworld_simple_note_count_bucket_list_status | 1 | 0 | 0 | 1 |
| 7847649_3 | appworld_simple_note_count_bucket_list_status | 1 | 0 | 0 | 1 |
| 552869a_1 | appworld_venmo_sum_year_bill_payments | 1 | 0 | 0 | 1 |
| 552869a_2 | appworld_venmo_sum_year_bill_payments | 1 | 0 | 0 | 1 |
| 552869a_3 | appworld_venmo_sum_year_bill_payments | 1 | 0 | 0 | 1 |
| 652485c_1 | appworld_spotify_public_liked_library_playlist_share | 1 | 0 | 0 | 1 |
| 652485c_2 | appworld_spotify_public_liked_library_playlist_share | 1 | 0 | 0 | 1 |
| 652485c_3 | appworld_spotify_public_liked_library_playlist_share | 1 | 0 | 0 | 1 |
| ccf4b82_1 | appworld_venmo_approve_requests_and_withdraw_balance | 1 | 0 | 0 | 1 |
| ccf4b82_2 | appworld_venmo_approve_requests_and_withdraw_balance | 1 | 0 | 0 | 1 |
| ccf4b82_3 | appworld_venmo_approve_requests_and_withdraw_balance | 1 | 0 | 0 | 1 |
| 522e5e5_1 | appworld_venmo_friend_transaction_counterparties | 1 | 0 | 0 | 1 |
| 522e5e5_2 | appworld_venmo_friend_transaction_counterparties | 1 | 0 | 0 | 1 |
| 522e5e5_3 | appworld_venmo_friend_transaction_counterparties | 1 | 0 | 0 | 1 |
| 0de03ea_1 | appworld_spotify_play_offline_downloaded_collection | 1 | 0 | 0 | 1 |
| 0de03ea_2 | appworld_spotify_play_offline_downloaded_collection | 1 | 0 | 0 | 1 |
| 0de03ea_3 | appworld_spotify_play_offline_downloaded_collection | 1 | 0 | 0 | 1 |
| 2c544f9_1 | appworld_venmo_send_to_named_user | 1 | 2 | 0 | 1 |
| 2c544f9_2 | appworld_venmo_send_to_named_user | 1 | 2 | 0 | 1 |
| 2c544f9_3 | appworld_venmo_send_to_named_user | 1 | 2 | 0 | 1 |
| 270f1ff_1 | appworld_venmo_birthday_child_payment_and_text | 1 | 0 | 0 | 1 |
| 270f1ff_2 | appworld_venmo_birthday_child_payment_and_text | 1 | 0 | 0 | 1 |
| 270f1ff_3 | appworld_venmo_birthday_child_payment_and_text | 1 | 0 | 0 | 1 |
| 024c982_1 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 1 |
| 024c982_2 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 1 |
| 024c982_3 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 1 |
| 9ef798c_1 | appworld_venmo_accept_named_carpool_request_this_month | 1 | 0 | 0 | 1 |
| 9ef798c_2 | appworld_venmo_accept_named_carpool_request_this_month | 1 | 0 | 0 | 1 |
| 9ef798c_3 | appworld_venmo_accept_named_carpool_request_this_month | 1 | 0 | 0 | 1 |
| b9c5c9a_1 | appworld_file_update_reunion_rsvps_from_phone | 1 | 0 | 0 | 1 |
| b9c5c9a_2 | appworld_file_update_reunion_rsvps_from_phone | 1 | 0 | 0 | 1 |
| b9c5c9a_3 | appworld_file_update_reunion_rsvps_from_phone | 1 | 0 | 0 | 1 |
| 90adc3f_1 | appworld_venmo_correct_sent_requests_yesterday_evening | 1 | 0 | 0 | 1 |
| 90adc3f_2 | appworld_venmo_correct_sent_requests_yesterday_evening | 1 | 0 | 0 | 1 |
| 90adc3f_3 | appworld_venmo_correct_sent_requests_yesterday_evening | 1 | 0 | 0 | 1 |
| c77c005_1 | appworld_venmo_friend_transaction_counterparties | 1 | 0 | 0 | 1 |
| c77c005_2 | appworld_venmo_friend_transaction_counterparties | 1 | 0 | 0 | 1 |
| c77c005_3 | appworld_venmo_friend_transaction_counterparties | 1 | 0 | 0 | 1 |
| f323bae_1 | appworld_simple_note_export_habit_tracker_csv | 1 | 0 | 0 | 1 |
| f323bae_2 | appworld_simple_note_export_habit_tracker_csv | 1 | 0 | 0 | 1 |
| f323bae_3 | appworld_simple_note_export_habit_tracker_csv | 1 | 0 | 0 | 1 |
| 13547f5_1 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 1 |
| 13547f5_2 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 1 |
| 1150ed6_1 | appworld_spotify_play_released_year_from_collection | 1 | 0 | 0 | 1 |
| 1150ed6_2 | appworld_spotify_play_released_year_from_collection | 1 | 0 | 0 | 1 |
| 1150ed6_3 | appworld_spotify_play_released_year_from_collection | 1 | 0 | 0 | 1 |
| 31dc501_1 | appworld_phone_update_wake_alarm_snooze | 1 | 0 | 0 | 1 |
| 31dc501_2 | appworld_phone_update_wake_alarm_snooze | 1 | 0 | 0 | 1 |
| 31dc501_3 | appworld_phone_update_wake_alarm_snooze | 1 | 0 | 0 | 1 |
