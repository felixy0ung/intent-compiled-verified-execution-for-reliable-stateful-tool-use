# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 60 |
| success_rate | 0.6333 |
| supported_rate | 0.6833 |
| invalid_tool_calls_per_task | 0.3167 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 19.7833 |
| code_exec_calls_per_task | 0.6833 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 6131.7667 |
| completion_tokens_per_task | 24.95 |
| token_proxy_per_task | 6156.7167 |

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
| 2d9f728_1 | unsupported | 0 | 1 | 0 | 1 |
| 2d9f728_2 | unsupported | 0 | 1 | 0 | 1 |
| 2d9f728_3 | unsupported | 0 | 1 | 0 | 1 |
| 6f4b9a5_1 | unsupported | 0 | 1 | 0 | 1 |
| 6f4b9a5_2 | unsupported | 0 | 1 | 0 | 1 |
| 6f4b9a5_3 | unsupported | 0 | 1 | 0 | 1 |
| d6ac34d_1 | unsupported | 0 | 1 | 0 | 1 |
| d6ac34d_2 | unsupported | 0 | 1 | 0 | 1 |
| d6ac34d_3 | unsupported | 0 | 1 | 0 | 1 |
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
| 042a9fc_1 | unsupported | 0 | 1 | 0 | 1 |
| 042a9fc_2 | unsupported | 0 | 1 | 0 | 1 |
| 042a9fc_3 | unsupported | 0 | 1 | 0 | 1 |
| cef9191_1 | appworld_spotify_followed_artist_follower_extreme | 1 | 0 | 0 | 1 |
| cef9191_2 | appworld_spotify_followed_artist_follower_extreme | 1 | 0 | 0 | 1 |
| cef9191_3 | appworld_spotify_followed_artist_follower_extreme | 1 | 0 | 0 | 1 |
| 3b8fb7a_1 | unsupported | 0 | 1 | 0 | 1 |
| 3b8fb7a_2 | unsupported | 0 | 1 | 0 | 1 |
| 3b8fb7a_3 | unsupported | 0 | 1 | 0 | 1 |
| afc4005_1 | unsupported | 0 | 1 | 0 | 1 |
| afc4005_2 | unsupported | 0 | 1 | 0 | 1 |
| afc4005_3 | unsupported | 0 | 1 | 0 | 1 |
| 9dabbc9_1 | unsupported | 0 | 1 | 0 | 1 |
| 9dabbc9_2 | appworld_venmo_process_pending_payment_requests | 0 | 0 | 0 | 1 |
| 9dabbc9_3 | appworld_venmo_process_pending_payment_requests | 0 | 0 | 0 | 1 |
| 425a494_1 | appworld_spotify_liked_genre_extreme | 1 | 0 | 0 | 1 |
| 425a494_2 | appworld_spotify_liked_genre_extreme | 1 | 0 | 0 | 1 |
| 425a494_3 | appworld_spotify_liked_genre_extreme | 1 | 0 | 0 | 1 |
