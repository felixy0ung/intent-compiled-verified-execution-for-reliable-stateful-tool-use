# AppWorld Static Instruction-Coverage Audit

This audit reads public AppWorld task IDs and public `specs.json` instructions,
then runs only the ICVE registry compile step. It does not start AppWorld, execute
tools, inspect databases, or load ground-truth files. The numbers below are
compile/coverage diagnostics, not task-success or leaderboard metrics.

## Summary

| metric | value |
| --- | ---: |
| registered_appworld_machines | 88 |
| total_tasks | 585 |
| compiled | 192 |
| dispatchable | 192 |
| unsupported | 393 |
| compiled_rate | 0.3282 |
| dispatchable_rate | 0.3282 |
| dispatchable_scenarios | 64 / 195 |

## By Split

| split | tasks | compiled | dispatchable | unsupported | dispatchable rate | dispatchable scenarios |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| test_challenge | 417 | 24 | 24 | 393 | 0.0576 | 8 / 139 |
| test_normal | 168 | 168 | 168 | 0 | 1.0000 | 56 / 56 |

## Top Dispatchable Intents

| intent_type | tasks |
| --- | ---: |
| appworld_venmo_friend_transaction_counterparties | 6 |
| appworld_amazon_order_product_type_from_saved_list | 6 |
| appworld_venmo_reset_friends_to_phone_friends | 3 |
| appworld_spotify_filter_queue_by_liked_status | 3 |
| appworld_spotify_navigate_until_private_status | 3 |
| appworld_file_reorganize_dated_meeting_files | 3 |
| appworld_venmo_sum_month_transactions | 3 |
| appworld_spotify_archive_playlist_songs_from_file | 3 |
| appworld_spotify_reset_queue_with_recommendations | 3 |
| appworld_venmo_settle_roommate_dinner | 3 |
| appworld_simple_note_fill_liked_song_release_months | 3 |
| appworld_simple_note_add_today_habit_log | 3 |

## Top Unsupported Buckets

| bucket | tasks |
| --- | ---: |
| amazon_purchase_or_product_search | 206 |
| gmail_email | 113 |
| splitwise_vacation_or_expense | 28 |
| spotify_music | 26 |
| venmo_payment_or_request | 17 |
| phone_message | 3 |

## Coverage Roadmap

The roadmap is derived from unsupported public-instruction buckets. It is
not a solved-coverage result; it records what new machine capabilities and
validation gates would be required before claiming support for each bucket.
Full rows are in `coverage_roadmap.csv`.

| split | bucket | tasks | scenarios | roadmap family |
| --- | --- | ---: | ---: | --- |
| test_challenge | amazon_purchase_or_product_search | 206 | 72 | Amazon search-and-purchase machines |
| test_challenge | gmail_email | 113 | 38 | Gmail thread-and-draft machines |
| test_challenge | splitwise_vacation_or_expense | 28 | 10 | Splitwise expense-settlement machines |
| test_challenge | spotify_music | 26 | 11 | Spotify search-and-library machines |
| test_challenge | venmo_payment_or_request | 17 | 7 | Venmo payment/request machines |
| test_challenge | phone_message | 3 | 1 | Phone messaging machines |

## Scenario Coverage

- Fully dispatchable scenarios: 64
- Partially dispatchable scenarios: 0
- Full per-scenario rows are in `scenario_coverage.csv`.

Interpretation: a dispatchable compile means the current registry recognized the
instruction and produced a complete typed frame. Unsupported rows are explicit
coverage gaps that should remain no-action outcomes unless a new machine is
added and validated.
