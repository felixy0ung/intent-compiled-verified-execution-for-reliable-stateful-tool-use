# AppWorld Machine Development-Cost Table

This table is generated from `src/pctu_pilot/appworld_agents.py` and the local
`test_normal.txt` diagnostic. It records every registered AppWorld `IntentMachine`.
Historical wall-clock adaptation time was not logged, so the field is explicitly
`not_recorded`; compiler/handler LOC, slots, shared API namespaces, and covered task
counts are reproducible proxies for development cost and reuse.

- Registered AppWorld machines: 93
- Used by full168 supported tasks: 55
- Supported tasks: 168
- Tasks per used machine: 3.05
- Median slots / compiler LOC / handler LOC / total LOC: 1.0 / 18.0 / 74.0 / 94.0

| intent_type | slots | compiler LOC | handler LOC | covered tasks | shared APIs | adaptation time |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| appworld_venmo_friend_transaction_counterparties | 2 | 20 | 65 | 6 | supervisor,venmo | not_recorded |
| appworld_file_delete_downloads_by_extension | 1 | 16 | 32 | 3 | file_system,supervisor | not_recorded |
| appworld_file_reorganize_dated_meeting_files | 1 | 18 | 51 | 3 | file_system,supervisor | not_recorded |
| appworld_file_update_reunion_rsvps_from_phone | 1 | 17 | 156 | 3 | file_system,phone,supervisor | not_recorded |
| appworld_pay_csv_debts_via_venmo_or_splitwise | 2 | 22 | 182 | 3 | file_system,splitwise,supervisor,venmo | not_recorded |
| appworld_phone_reply_favorite_recipe_to_relationship | 1 | 18 | 60 | 3 | phone,simple_note,supervisor | not_recorded |
| appworld_phone_send_message_to_relationship | 3 | 20 | 51 | 3 | phone,supervisor | not_recorded |
| appworld_phone_update_wake_alarm_snooze | 2 | 17 | 42 | 3 | phone,supervisor | not_recorded |
| appworld_simple_note_add_today_habit_log | 2 | 32 | 74 | 3 | simple_note,supervisor | not_recorded |
| appworld_simple_note_count_bucket_list_status | 1 | 17 | 55 | 3 | simple_note,supervisor | not_recorded |
| appworld_simple_note_export_habit_tracker_csv | 2 | 22 | 77 | 3 | file_system,simple_note,supervisor | not_recorded |
| appworld_simple_note_fill_liked_song_release_months | 0 | 14 | 121 | 3 | simple_note,spotify,supervisor | not_recorded |
| appworld_simple_note_import_markdown_files | 1 | 19 | 40 | 3 | file_system,simple_note,supervisor | not_recorded |
| appworld_simple_note_longest_habit_streak | 1 | 17 | 62 | 3 | simple_note,supervisor | not_recorded |
| appworld_simple_note_random_quote | 1 | 16 | 56 | 3 | simple_note,supervisor | not_recorded |
| appworld_simple_note_update_monthly_venmo_expense | 0 | 13 | 79 | 3 | simple_note,supervisor,venmo | not_recorded |
| appworld_simple_note_workout_duration | 1 | 16 | 68 | 3 | simple_note,supervisor | not_recorded |
| appworld_splitwise_accept_known_phone_invitations | 2 | 22 | 119 | 3 | phone,splitwise,supervisor | not_recorded |
| appworld_splitwise_record_trip_expenses_from_simple_note | 1 | 18 | 190 | 3 | phone,simple_note,splitwise,supervisor | not_recorded |
| appworld_splitwise_record_venmo_receipt_payments | 1 | 18 | 131 | 3 | splitwise,supervisor,venmo | not_recorded |
| appworld_spotify_append_most_common_playlist_genre | 0 | 14 | 47 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_apply_phone_playlist_suggestions | 1 | 18 | 154 | 3 | phone,spotify,supervisor | not_recorded |
| appworld_spotify_apply_todoist_playlist_suggestions | 3 | 22 | 254 | 3 | phone,spotify,supervisor,todoist | not_recorded |
| appworld_spotify_archive_playlist_songs_from_file | 2 | 18 | 77 | 3 | file_system,spotify,supervisor | not_recorded |
| appworld_spotify_filter_queue_by_liked_status | 1 | 20 | 40 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_followed_artist_follower_extreme | 1 | 15 | 30 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_like_all_library_items | 0 | 12 | 49 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_liked_genre_extreme | 2 | 24 | 64 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_navigate_until_private_status | 2 | 19 | 44 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_play_offline_downloaded_collection | 2 | 21 | 74 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_play_released_year_from_collection | 2 | 24 | 51 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_playlist_artist_song_count_extreme | 2 | 18 | 41 | 3 | spotify,supervisor | not_recorded |
| appworld_spotify_playlist_from_recent_simple_note | 1 | 16 | 122 | 3 | simple_note,spotify,supervisor | not_recorded |
| appworld_spotify_public_liked_library_playlist_share | 1 | 17 | 77 | 3 | phone,spotify,supervisor | not_recorded |
| appworld_spotify_reset_queue_with_recommendations | 0 | 12 | 26 | 3 | spotify,supervisor | not_recorded |
| appworld_todoist_fill_today_from_schedule | 1 | 21 | 191 | 3 | simple_note,supervisor,todoist | not_recorded |
| appworld_todoist_reassign_accepted_takeover_tasks | 1 | 20 | 101 | 3 | supervisor,todoist | not_recorded |
| appworld_venmo_accept_named_carpool_request_this_month | 1 | 16 | 130 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_add_friends_by_relationships | 1 | 18 | 54 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_approve_requests_and_withdraw_balance | 2 | 19 | 86 | 3 | supervisor,venmo | not_recorded |
| appworld_venmo_approve_roommate_requests_this_month | 0 | 12 | 126 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_birthday_child_payment_and_text | 4 | 28 | 181 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_correct_housing_bill_request | 3 | 20 | 92 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_correct_sent_requests_yesterday_evening | 3 | 24 | 93 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_count_friends_since_month_start | 2 | 22 | 50 | 3 | supervisor,venmo | not_recorded |
| appworld_venmo_request_money_from_contact | 5 | 24 | 73 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_reset_friends_to_phone_friends | 0 | 13 | 42 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_send_to_each_relationship_with_refill | 3 | 21 | 110 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_send_to_named_user | 2 | 16 | 139 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_settle_roommate_dinner | 5 | 24 | 172 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_settle_trip_note_debts | 3 | 20 | 246 | 3 | phone,simple_note,supervisor,venmo | not_recorded |
| appworld_venmo_signup_missing_relationship_accounts | 3 | 23 | 75 | 3 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_sum_month_transactions | 1 | 17 | 41 | 3 | supervisor,venmo | not_recorded |
| appworld_venmo_sum_recent_received_requests | 1 | 16 | 33 | 3 | supervisor,venmo | not_recorded |
| appworld_venmo_sum_year_bill_payments | 1 | 16 | 36 | 3 | supervisor,venmo | not_recorded |
| appworld_amazon_move_product_type_between_saved_lists | 3 | 18 | 58 | 0 | amazon,supervisor | not_recorded |
| appworld_amazon_move_rating_filtered_products | 4 | 20 | 58 | 0 | amazon,supervisor | not_recorded |
| appworld_amazon_order_product_type_from_saved_list | 4 | 19 | 114 | 0 | amazon,supervisor | not_recorded |
| appworld_amazon_purchase_phone_recommendation | 4 | 19 | 250 | 0 | amazon,phone,supervisor | not_recorded |
| appworld_bucket_list_status_update | 2 | 16 | 51 | 0 | simple_note,supervisor | not_recorded |
| appworld_delete_gmail_empty_drafts | 1 | 16 | 39 | 0 | gmail,supervisor | not_recorded |
| appworld_delete_phone_spam_messages | 1 | 15 | 44 | 0 | phone,supervisor | not_recorded |
| appworld_file_prefix_and_move_old_files | 3 | 20 | 61 | 0 | file_system,supervisor | not_recorded |
| appworld_gmail_star_threads_by_relationship | 1 | 20 | 96 | 0 | gmail,phone,supervisor | not_recorded |
| appworld_gmail_thread_cleanup | 2 | 18 | 63 | 0 | gmail,supervisor | not_recorded |
| appworld_phone_message_app_account_verify_reset | 3 | 20 | 185 | 0 | gmail,phone,supervisor | not_recorded |
| appworld_phone_message_non_venmo_contacts | 3 | 18 | 48 | 0 | phone,supervisor,venmo | not_recorded |
| appworld_remove_expired_payment_cards | 0 | 12 | 46 | 0 | supervisor | not_recorded |
| appworld_simple_note_export_markdown | 1 | 17 | 50 | 0 | file_system,simple_note,supervisor | not_recorded |
| appworld_spotify_add_artist_playcount_songs_to_queue | 2 | 17 | 47 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_count_recent_release_library_songs | 2 | 37 | 50 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_count_unique_library_songs | 0 | 13 | 35 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_current_artist_followers | 0 | 12 | 21 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_download_liked_library_songs | 1 | 22 | 61 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_follow_artists_by_genre_followers | 2 | 17 | 33 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_follow_artists_from_liked_songs_and_albums | 0 | 12 | 37 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_follow_playlist_song_artists_by_genre | 1 | 15 | 40 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_like_songs_from_followed_artists | 0 | 12 | 42 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_navigate_until_artist | 2 | 17 | 46 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_playlist_best_song_per_collection | 3 | 22 | 67 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_playlist_from_workout_email | 1 | 16 | 154 | 0 | gmail,spotify,supervisor | not_recorded |
| appworld_spotify_rate_library_songs_by_liked_status | 3 | 29 | 82 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_reply_liked_song_recommendations_email | 2 | 23 | 129 | 0 | gmail,phone,spotify,supervisor | not_recorded |
| appworld_spotify_sync_following_by_liked_song_artists | 1 | 24 | 49 | 0 | spotify,supervisor | not_recorded |
| appworld_spotify_top_played_genre_titles | 2 | 18 | 50 | 0 | spotify,supervisor | not_recorded |
| appworld_venmo_change_password | 1 | 18 | 75 | 0 | gmail,supervisor,venmo | not_recorded |
| appworld_venmo_like_transactions_by_relationship_period | 2 | 17 | 64 | 0 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_manager_meal_total_from_social_feed | 4 | 22 | 85 | 0 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_pay_grocery_from_text_and_notify | 3 | 20 | 104 | 0 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_process_pending_payment_requests | 2 | 20 | 79 | 0 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_remind_old_payment_requests | 2 | 19 | 50 | 0 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_send_to_phone_number | 3 | 18 | 72 | 0 | phone,supervisor,venmo | not_recorded |
| appworld_venmo_sum_transaction_likes | 2 | 18 | 43 | 0 | supervisor,venmo | not_recorded |
