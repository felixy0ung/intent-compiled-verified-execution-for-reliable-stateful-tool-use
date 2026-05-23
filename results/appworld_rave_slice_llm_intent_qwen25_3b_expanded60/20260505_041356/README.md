# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 60 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0833 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 20.1833 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 2792.4 |
| completion_tokens_per_task | 31.5667 |
| token_proxy_per_task | 2823.9667 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 0d8a4ee_3 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 13547f5_1 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 1 |
| 13547f5_2 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 1 |
| 13547f5_3 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 1 |
| 37a8675_1 | appworld_venmo_send_to_phone_number | 1 | 3 | 0 | 1 |
| 37a8675_2 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 1 |
| 37a8675_3 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 1 |
| 024c982_1 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 1 |
| 024c982_2 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 1 |
| 024c982_3 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 1 |
| 4fab96f_1 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 1 |
| 4fab96f_2 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 1 |
| 4fab96f_3 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 1 |
| 6ea6792_1 | appworld_venmo_process_pending_payment_requests | 1 | 0 | 0 | 1 |
| 6ea6792_2 | appworld_venmo_process_pending_payment_requests | 1 | 0 | 0 | 1 |
| 6ea6792_3 | appworld_venmo_process_pending_payment_requests | 1 | 0 | 0 | 1 |
| ff58e36_1 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 1 |
| ff58e36_2 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 1 |
| ff58e36_3 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 1 |
| 5e27cd7_1 | appworld_delete_gmail_empty_drafts | 1 | 0 | 0 | 1 |
| 5e27cd7_2 | appworld_delete_gmail_empty_drafts | 1 | 0 | 0 | 1 |
| 5e27cd7_3 | appworld_delete_gmail_empty_drafts | 1 | 0 | 0 | 1 |
| 09ac073_1 | appworld_gmail_thread_cleanup | 1 | 0 | 0 | 1 |
| 09ac073_2 | appworld_gmail_thread_cleanup | 1 | 0 | 0 | 1 |
| 09ac073_3 | appworld_gmail_thread_cleanup | 1 | 0 | 0 | 1 |
| 771d8fc_1 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 1 |
| 771d8fc_2 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 1 |
| 771d8fc_3 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 1 |
| cf6abd2_1 | appworld_bucket_list_status_update | 1 | 0 | 0 | 1 |
| cf6abd2_2 | appworld_bucket_list_status_update | 1 | 0 | 0 | 1 |
| cf6abd2_3 | appworld_bucket_list_status_update | 1 | 0 | 0 | 1 |
| 07b42fd_1 | appworld_spotify_follow_artists_by_genre_followers | 1 | 0 | 0 | 1 |
| 07b42fd_2 | appworld_spotify_follow_artists_by_genre_followers | 1 | 0 | 0 | 1 |
| 07b42fd_3 | appworld_spotify_follow_artists_by_genre_followers | 1 | 0 | 0 | 1 |
| aa8502b_1 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 1 |
| aa8502b_2 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 1 |
| aa8502b_3 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 1 |
| 6171bbc_1 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 1 |
| 6171bbc_2 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 1 |
| 6171bbc_3 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 1 |
| f3f60f0_1 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 1 |
| f3f60f0_2 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 1 |
| f3f60f0_3 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 1 |
| 3ab5b8b_1 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 1 |
| 3ab5b8b_2 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 1 |
| 3ab5b8b_3 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 1 |
| 692c77d_1 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 1 |
| 692c77d_2 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 1 |
| 692c77d_3 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 1 |
| 31dc501_1 | appworld_phone_update_wake_alarm_snooze | 1 | 0 | 0 | 1 |
| 31dc501_2 | appworld_phone_update_wake_alarm_snooze | 1 | 0 | 0 | 1 |
| 31dc501_3 | appworld_phone_update_wake_alarm_snooze | 1 | 0 | 0 | 1 |
| 07bb666_1 | appworld_amazon_move_rating_filtered_products | 1 | 0 | 0 | 1 |
| 07bb666_2 | appworld_amazon_move_rating_filtered_products | 1 | 0 | 0 | 1 |
| 07bb666_3 | appworld_amazon_move_rating_filtered_products | 1 | 0 | 0 | 1 |
| 396c5a2_1 | appworld_spotify_add_artist_playcount_songs_to_queue | 1 | 0 | 0 | 1 |
| 396c5a2_2 | appworld_spotify_add_artist_playcount_songs_to_queue | 1 | 0 | 0 | 1 |
| 396c5a2_3 | appworld_spotify_add_artist_playcount_songs_to_queue | 1 | 0 | 0 | 1 |
