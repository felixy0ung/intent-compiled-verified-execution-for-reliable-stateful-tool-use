# AppWorld RAVE Slice

This run evaluates a targeted public AppWorld stateful slice with typed RAVE intent compilers.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_slice |
| episodes | 51 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.098 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 21.9412 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 0.0 |
| prompt_tokens_per_task | 0.0 |
| completion_tokens_per_task | 0.0 |
| token_proxy_per_task | 184.8431 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 0d8a4ee_1 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 0 |
| 0d8a4ee_2 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 0 |
| 0d8a4ee_3 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 0 |
| 13547f5_1 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 0 |
| 13547f5_2 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 0 |
| 13547f5_3 | appworld_phone_send_message_to_relationship | 1 | 0 | 0 | 0 |
| 37a8675_1 | appworld_venmo_send_to_phone_number | 1 | 3 | 0 | 0 |
| 37a8675_2 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 0 |
| 37a8675_3 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 0 |
| 024c982_1 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 0 |
| 024c982_2 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 0 |
| 024c982_3 | appworld_venmo_request_money_from_contact | 1 | 0 | 0 | 0 |
| 4fab96f_1 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 0 |
| 4fab96f_2 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 0 |
| 4fab96f_3 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 0 |
| 6ea6792_1 | appworld_venmo_process_pending_payment_requests | 1 | 0 | 0 | 0 |
| 6ea6792_2 | appworld_venmo_process_pending_payment_requests | 1 | 0 | 0 | 0 |
| 6ea6792_3 | appworld_venmo_process_pending_payment_requests | 1 | 0 | 0 | 0 |
| ff58e36_1 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 0 |
| ff58e36_2 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 0 |
| ff58e36_3 | appworld_venmo_add_friends_by_relationships | 1 | 0 | 0 | 0 |
| 5e27cd7_1 | appworld_delete_gmail_empty_drafts | 1 | 0 | 0 | 0 |
| 5e27cd7_2 | appworld_delete_gmail_empty_drafts | 1 | 0 | 0 | 0 |
| 5e27cd7_3 | appworld_delete_gmail_empty_drafts | 1 | 0 | 0 | 0 |
| 09ac073_1 | appworld_gmail_thread_cleanup | 1 | 0 | 0 | 0 |
| 09ac073_2 | appworld_gmail_thread_cleanup | 1 | 0 | 0 | 0 |
| 09ac073_3 | appworld_gmail_thread_cleanup | 1 | 0 | 0 | 0 |
| 771d8fc_1 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 0 |
| 771d8fc_2 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 0 |
| 771d8fc_3 | appworld_delete_phone_spam_messages | 1 | 0 | 0 | 0 |
| cf6abd2_1 | appworld_bucket_list_status_update | 1 | 0 | 0 | 0 |
| cf6abd2_2 | appworld_bucket_list_status_update | 1 | 0 | 0 | 0 |
| cf6abd2_3 | appworld_bucket_list_status_update | 1 | 0 | 0 | 0 |
| 07b42fd_1 | appworld_spotify_follow_artists_by_genre_followers | 1 | 0 | 0 | 0 |
| 07b42fd_2 | appworld_spotify_follow_artists_by_genre_followers | 1 | 0 | 0 | 0 |
| 07b42fd_3 | appworld_spotify_follow_artists_by_genre_followers | 1 | 0 | 0 | 0 |
| aa8502b_1 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 0 |
| aa8502b_2 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 0 |
| aa8502b_3 | appworld_spotify_sync_following_by_liked_song_artists | 1 | 0 | 0 | 0 |
| 6171bbc_1 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 0 |
| 6171bbc_2 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 0 |
| 6171bbc_3 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 0 |
| f3f60f0_1 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 0 |
| f3f60f0_2 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 0 |
| f3f60f0_3 | appworld_spotify_like_all_library_items | 1 | 0 | 0 | 0 |
| 3ab5b8b_1 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 0 |
| 3ab5b8b_2 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 0 |
| 3ab5b8b_3 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 0 |
| 692c77d_1 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 0 |
| 692c77d_2 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 0 |
| 692c77d_3 | appworld_spotify_rate_library_songs_by_liked_status | 1 | 0 | 0 | 0 |
