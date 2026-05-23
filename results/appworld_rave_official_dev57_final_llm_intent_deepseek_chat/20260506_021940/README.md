# AppWorld RAVE Slice

This run evaluates real-LLM typed intent extraction with the verified RAVE AppWorld runtime on the targeted public stateful slice.
It is not a full AppWorld leaderboard run.

## Summary

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 57 |
| success_rate | 1.0 |
| supported_rate | 1.0 |
| invalid_tool_calls_per_task | 0.0351 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 47.4737 |
| code_exec_calls_per_task | 1.0 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 4947.0 |
| completion_tokens_per_task | 35.386 |
| token_proxy_per_task | 4982.386 |

## Episodes

| task_id | intent_type | success | invalid | unsafe | llm_calls |
| --- | --- | --- | --- | --- | --- |
| 50e1ac9_1 | appworld_spotify_top_played_genre_titles | 1 | 0 | 0 | 1 |
| 50e1ac9_2 | appworld_spotify_top_played_genre_titles | 1 | 0 | 0 | 1 |
| 50e1ac9_3 | appworld_spotify_top_played_genre_titles | 1 | 0 | 0 | 1 |
| fac291d_1 | appworld_spotify_count_unique_library_songs | 1 | 0 | 0 | 1 |
| fac291d_2 | appworld_spotify_count_unique_library_songs | 1 | 0 | 0 | 1 |
| fac291d_3 | appworld_spotify_count_unique_library_songs | 1 | 0 | 0 | 1 |
| 530b157_1 | appworld_venmo_pay_grocery_from_text_and_notify | 1 | 0 | 0 | 1 |
| 530b157_2 | appworld_venmo_pay_grocery_from_text_and_notify | 1 | 0 | 0 | 1 |
| 530b157_3 | appworld_venmo_pay_grocery_from_text_and_notify | 1 | 0 | 0 | 1 |
| 4ec8de5_1 | appworld_spotify_count_recent_release_library_songs | 1 | 0 | 0 | 1 |
| 4ec8de5_2 | appworld_spotify_count_recent_release_library_songs | 1 | 0 | 0 | 1 |
| 4ec8de5_3 | appworld_spotify_count_recent_release_library_songs | 1 | 0 | 0 | 1 |
| b119b1f_1 | appworld_spotify_navigate_until_artist | 1 | 0 | 0 | 1 |
| b119b1f_2 | appworld_spotify_navigate_until_artist | 1 | 0 | 0 | 1 |
| b119b1f_3 | appworld_spotify_navigate_until_artist | 1 | 0 | 0 | 1 |
| d4e9306_1 | appworld_spotify_follow_artists_from_liked_songs_and_albums | 1 | 0 | 0 | 1 |
| d4e9306_2 | appworld_spotify_follow_artists_from_liked_songs_and_albums | 1 | 0 | 0 | 1 |
| d4e9306_3 | appworld_spotify_follow_artists_from_liked_songs_and_albums | 1 | 0 | 0 | 1 |
| 0d8a4ee_1 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 0d8a4ee_2 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 0d8a4ee_3 | appworld_phone_message_non_venmo_contacts | 1 | 0 | 0 | 1 |
| 37a8675_1 | appworld_venmo_send_to_phone_number | 1 | 0 | 0 | 1 |
| 37a8675_2 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 1 |
| 37a8675_3 | appworld_venmo_send_to_phone_number | 1 | 1 | 0 | 1 |
| 3ab5b8b_1 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 1 |
| 3ab5b8b_2 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 1 |
| 3ab5b8b_3 | appworld_spotify_download_liked_library_songs | 1 | 0 | 0 | 1 |
| df61dc5_1 | appworld_venmo_like_transactions_by_relationship_period | 1 | 0 | 0 | 1 |
| df61dc5_2 | appworld_venmo_like_transactions_by_relationship_period | 1 | 0 | 0 | 1 |
| df61dc5_3 | appworld_venmo_like_transactions_by_relationship_period | 1 | 0 | 0 | 1 |
| 383cbac_1 | appworld_venmo_manager_meal_total_from_social_feed | 1 | 0 | 0 | 1 |
| 383cbac_2 | appworld_venmo_manager_meal_total_from_social_feed | 1 | 0 | 0 | 1 |
| 383cbac_3 | appworld_venmo_manager_meal_total_from_social_feed | 1 | 0 | 0 | 1 |
| 23cf851_1 | appworld_venmo_sum_transaction_likes | 1 | 0 | 0 | 1 |
| 23cf851_2 | appworld_venmo_sum_transaction_likes | 1 | 0 | 0 | 1 |
| 23cf851_3 | appworld_venmo_sum_transaction_likes | 1 | 0 | 0 | 1 |
| 57c3486_1 | appworld_spotify_like_songs_from_followed_artists | 1 | 0 | 0 | 1 |
| 57c3486_2 | appworld_spotify_like_songs_from_followed_artists | 1 | 0 | 0 | 1 |
| 57c3486_3 | appworld_spotify_like_songs_from_followed_artists | 1 | 0 | 0 | 1 |
| 68ee2c9_1 | appworld_file_prefix_and_move_old_files | 1 | 0 | 0 | 1 |
| 68ee2c9_2 | appworld_file_prefix_and_move_old_files | 1 | 0 | 0 | 1 |
| 68ee2c9_3 | appworld_file_prefix_and_move_old_files | 1 | 0 | 0 | 1 |
| 6bdbc26_1 | appworld_spotify_current_artist_followers | 1 | 0 | 0 | 1 |
| 6bdbc26_2 | appworld_spotify_current_artist_followers | 1 | 0 | 0 | 1 |
| 6bdbc26_3 | appworld_spotify_current_artist_followers | 1 | 0 | 0 | 1 |
| 6171bbc_1 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 1 |
| 6171bbc_2 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 1 |
| 6171bbc_3 | appworld_spotify_playlist_best_song_per_collection | 1 | 0 | 0 | 1 |
| 6c2c621_1 | appworld_simple_note_export_markdown | 1 | 0 | 0 | 1 |
| 6c2c621_2 | appworld_simple_note_export_markdown | 1 | 0 | 0 | 1 |
| 6c2c621_3 | appworld_simple_note_export_markdown | 1 | 0 | 0 | 1 |
| 396c5a2_1 | appworld_spotify_add_artist_playcount_songs_to_queue | 1 | 0 | 0 | 1 |
| 396c5a2_2 | appworld_spotify_add_artist_playcount_songs_to_queue | 1 | 0 | 0 | 1 |
| 396c5a2_3 | appworld_spotify_add_artist_playcount_songs_to_queue | 1 | 0 | 0 | 1 |
| 4fab96f_1 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 1 |
| 4fab96f_2 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 1 |
| 4fab96f_3 | appworld_venmo_remind_old_payment_requests | 1 | 0 | 0 | 1 |
