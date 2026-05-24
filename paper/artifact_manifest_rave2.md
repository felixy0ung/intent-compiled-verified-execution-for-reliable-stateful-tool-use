# ICVE Artifact Manifest

This manifest records the files and commands needed to reproduce the current
Intent-Compiled Verified Execution (ICVE) paper claims. The package name `pctu_pilot`
and many `rave` paths are historical; the active method name in the paper is ICVE.

## Environment

Use the local conda environment:

```bash
<CONDA_ROOT>/bin/conda run -p <CONDA_ROOT>/envs/pctu-sim python --version
```

Core assumptions:

- Python environment: `<CONDA_ROOT>/envs/pctu-sim`
- AppWorld packaged-evaluator environment: `<CONDA_ROOT>/envs/pctu-appworld`
- Isolated latest official AppWorld agent-runner attempt environment:
  `<CONDA_ROOT>/envs/pctu-appworld-agents`
- Isolated AppWorld 0.2.0 data root for official-runner smoke/dev10/dev10_full50:
  `<PROJECT_ROOT>/appworld_020_root`
- GPU used for local model runs: NVIDIA RTX 3080 Ti, 12GB
- Paper compiler: Tectonic 0.16.9 in `pctu-sim`

## Anonymous Supplement Package

An anonymized, whitelist-based supplement package can be rebuilt with:

```bash
<CONDA_ROOT>/bin/conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/build_anonymous_supplement.py
```

Current outputs:

- `artifacts/rave2_emnlp2026_arr_anonymous_supplement/`
- `artifacts/rave2_emnlp2026_arr_anonymous_supplement.tar.gz`

The package includes source code, experiment scripts, environment examples, paper source
and PDF, dataset-id lists, summary/evaluator outputs, and this manifest. It excludes real
API-key `.env` files, raw AppWorld task logs, JSONL logs, database snapshots, downloaded
bundles, local conda environments, and model caches. The builder replaces absolute local
paths in copied text files with `<PROJECT_ROOT>`, `<CONDA_ROOT>`, or `<HOME>`.

## Artifact Licensing and Redistribution Notes

The supplement is a summary-level research artifact. It includes the ICVE source,
experiment scripts, public task-id lists, result summaries, and evaluator summaries. It
does not redistribute AppWorld's protected encrypted bundle, raw AppWorld databases,
access tokens, raw task logs, or downloaded data bundles. The local `data/LICENSE` and
`data/README_BEFORE_SHARING.md` files document AppWorld's protected-data condition: the
protected AppWorld bundle is released under Apache 2.0 with an additional requirement
that public redistribution of that protected content or derivatives be encrypted. This
supplement avoids redistributing that protected content directly; users should obtain
AppWorld through its official release channel and respect its license and redistribution
terms.

## Compute and Runtime Notes

No model training or fine-tuning is performed. Local model experiments use temperature 0
inference on one NVIDIA RTX 3080 Ti GPU with 12GB memory. Qwen2.5-7B and Phi-3-mini are
run with 4-bit quantization; Qwen2.5-0.5B and Qwen2.5-3B are run as local instruction
models through an OpenAI-compatible server. Hosted DeepSeek-chat and DeepSeek-reasoner
replications use hosted API calls and do not consume local GPU time. Exact aggregate
wall-clock and GPU-hour totals were not recorded uniformly across all exploratory and
final runs, so the artifact reports reproducible commands, task counts, model-call
counts, token proxies, and per-run result directories rather than a single total compute
number. The largest same-split official AppWorld baseline recorded in the paper, the
default-50-step DeepSeek ReAct-code dev57 run, completed in 75.9 minutes and used 879 LLM
calls and 6.45M tokens; ICVE dev57 rows use deterministic execution or one intent
extraction call per task plus the runtime-checked executor.

## Method Code

- `src/pctu_pilot/rave_dsl.py`: typed intent frames, schemas, machines, and runtime
  action types.
- `src/pctu_pilot/rave_runtime.py`: benchmark-agnostic registry runtime plus
  `RaveStateLedger` and `RaveRuntimePolicy` interfaces.
- `src/pctu_pilot/toolsandbox_agents.py`: ToolSandbox binding, 13 registered
  `IntentMachine`s, concrete `ToolSandboxRuntimePolicy`, and a restricted dynamic
  setting-machine synthesis prototype.
- `src/pctu_pilot/appworld_agents.py`: AppWorld binding with typed `IntentMachine`s for
  the targeted 72-task public slice and the complete local official AppWorld 0.2.0
  `dev.txt` split, plus real-LLM intent/slot-extraction and direct-code baselines.
- `experiments/run_toolsandbox_kill_criteria.py`: public ToolSandbox runner.
- `experiments/run_dynamic_synthesis_probe.py`: no-LLM ToolSandbox probe that disables
  the static registry and promotes dynamically synthesized setting machines only after
  shadow-mode, invariant, and counterexample checks.
- `experiments/run_dynamic_affordance_generalization.py`: no-LLM held-out
  synthetic-affordance diagnostic for inducing boolean setting machines from previously
  unseen `get_*_status` / `set_*_status(on: bool)` API pairs.
- `experiments/test_dynamic_machine_synthesis.py`: smoke tests for unsupported-frame
  logging, dynamic promotion, and unrelated-request rejection.
- `experiments/run_appworld_rave_slice.py`: targeted public AppWorld slice runner with
  deterministic, `llm-intent`, `llm-code`, `llm-code-repair`, `llm-intent-code`, and
  `llm-react-code` modes, plus per-task flushing and resume support for hosted long
  runs.
- `experiments/combine_appworld_output_tasks.py`: combines hosted AppWorld
  `experiments/outputs/*/tasks` shards into a single evaluator-readable output
  directory, rejecting duplicate task ids.
- `data/datasets/rave_expanded66.txt`: historical AppWorld dataset file used to
  re-evaluate the preceding 66-task slice with AppWorld's packaged evaluator.
- `data/datasets/rave_expanded72.txt`: AppWorld dataset file used to re-evaluate the
  active 72-task slice with AppWorld's packaged evaluator.
- `experiments/run_frontier_toolsandbox_replication.sh`: frontier/OpenAI-compatible
  replication template.
- `experiments/summarize_rave2_statistics.py`: regenerates Wilson intervals and
  safety/cost means from recorded summaries.
- `experiments/summarize_icve_review_strengthening.py`: regenerates the
  failure-mode-shift, coverage-risk, and machine-coverage diagnostics used to support
  the added review-strengthening analysis.
- `experiments/build_anonymous_supplement.py`: builds the anonymized supplement
  directory and `.tar.gz` archive from a whitelist, excluding raw logs, database
  snapshots, downloaded bundles, local paths, and real API-key environment files.
- Paper Appendix A provides a claim-to-evidence matrix that maps each main paper claim to
  falsification criteria, concrete result locations, and the boundary under which the
  claim should be interpreted.
- Paper Appendix B provides a compact artifact and reproducibility map that points
  reviewers to the runtime modules, public runners, review-strengthening summaries, and
  full artifact index.

## Primary Results

- Qwen2.5-3B single-turn ToolSandbox:
  `results/toolsandbox_qwen25_3b_rave2_single_turn_compare_fixed/20260501_144845`
- Qwen2.5-3B insufficient-information ToolSandbox:
  `results/toolsandbox_qwen25_3b_rave2_insufficient_compare_fixed2/20260501_153424`
- Qwen2.5-0.5B scale checks:
  `results/toolsandbox_qwen25_05b_rave2_single_turn_compare_fixed/20260501_160536`
  and `results/toolsandbox_qwen25_05b_rave2_insufficient_compare/20260501_162021`
- Qwen2.5-7B-4bit scale checks:
  `results/toolsandbox_qwen25_7b_4bit_rave2_single_turn_compare_contact_name_patch/20260504_001328`
  and `results/toolsandbox_qwen25_7b_4bit_rave2_insufficient_compare_contact_name_patch/20260504_002013`
- Phi-3-mini cross-family diagnostics:
  `results/toolsandbox_phi3_mini_rave2_core10_compare/20260504_023509`
  and `results/toolsandbox_phi3_mini_rave2_insufficient10_compare/20260504_023708`
- Hosted DeepSeek-chat ToolSandbox replication:
  `results/frontier_toolsandbox_replication_deepseek/deepseek-chat_single_turn_patch_final/20260504_114435`
  and `results/frontier_toolsandbox_replication_deepseek/deepseek-chat_insufficient/20260504_041631`
- Hosted DeepSeek-reasoner ToolSandbox replication:
  `results/frontier_toolsandbox_replication_deepseek_reasoner/deepseek-reasoner_single_turn/20260504_122044`
  and `results/frontier_toolsandbox_replication_deepseek_reasoner/deepseek-reasoner_insufficient/20260504_124227`
- Dynamic affordance-template induction diagnostics:
  `results/dynamic_synthesis_probe/20260524_172425` covers five official ToolSandbox
  setting scenarios from an empty static registry, and
  `results/dynamic_affordance_generalization/20260524_172229` covers five held-out
  synthetic boolean-setting API pairs plus two rejection cases. The latter records 7/7
  expected outcomes, 5 promoted machines, 2 rejections, 0 LLM calls, and verified final
  state mutations for `bluetooth`, `dark_mode`, `privacy_mode`, `roaming_data`, and
  `auto_sync`.
- Review-strengthening diagnostics:
  `results/icve_review_strengthening/20260524` summarizes (i) MiniStore
  ReAct+schema/proof/verifier guardrail evidence via the PCTU ablation, (ii)
  ToolSandbox insufficient-information failure-mode shift from unsafe/invalid ReAct
  outcomes to zero unsafe and zero invalid ICVE outcomes, (iii) AppWorld
  `test_normal.txt` execution and static coverage-risk behavior with unsupported tasks
  left as no-action abstentions, and (iv) AppWorld machine coverage and development-cost
  statistics for the "not per-task scripts" analysis. The directory includes a full per-machine
  `machine_development_costs.csv`/`.md` table with slots, compiler/handler LOC,
  covered-task counts, shared API namespaces, shared runtime components, and
  `adaptation_time=not_recorded`.
- Static AppWorld public-instruction coverage audit:
  `results/appworld_static_coverage/20260524` reads only local AppWorld public
  `specs.json` instructions for all `test_normal.txt` and `test_challenge.txt` IDs,
  then runs the ICVE registry compile step without starting AppWorld, executing tools,
  inspecting databases, or loading ground truth. It compiles 168/168 `test_normal`
  instructions and 105/417 `test_challenge` instructions to complete frames. The same
  directory includes `coverage_roadmap.csv`, a derived roadmap that maps unsupported
  public-instruction buckets to required machine capabilities, non-coverage reasons, and
  validation gates.
- Held-out AppWorld phone-message account-verification slice:
  `results/appworld_phone_account_verify_reset_20260524/20260524_233807` records three
  local `test_challenge` tasks whose public instructions say that a child sent a phone
  message about app account creation. One general ICVE machine reads runtime-visible
  phone-message and Gmail verification/reset evidence, verifies the app account, resets
  its password, and reaches 3/3 success with 0 invalid calls and 0 unsafe state changes.
  This is a narrow held-out slice, not a full `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail relation-star slice:
  `results/appworld_gmail_star_relationship_20260524/20260525_000839` records three
  local `test_challenge` tasks whose public instructions ask to star every non-archived
  Gmail thread from or to a target contact relationship and unstar the rest. One general
  ICVE machine grounds the relationship through runtime-visible phone contacts, traverses
  non-archived Gmail thread categories, and reaches 3/3 success with 0 invalid calls and
  0 unsafe state changes. This is a narrow held-out slice, not a full `test_challenge`
  or leaderboard result.
- Held-out AppWorld expired-payment-card cleanup slice:
  `results/appworld_remove_expired_cards_20260525/20260525_002233` records three local
  `test_challenge` tasks whose public instructions ask to remove expired payment cards
  from all app accounts that have payment cards. One general cross-app ICVE machine
  checks Amazon, Spotify, and Venmo payment-card APIs through runtime-visible state,
  deletes expired cards, and reaches 3/3 success with 0 invalid calls and 0 unsafe state
  changes. This is a narrow held-out slice, not a full `test_challenge` or leaderboard
  result.
- Held-out AppWorld Venmo password-reset slice:
  `results/appworld_venmo_change_password_20260525/20260525_004717` records three local
  `test_challenge` tasks whose public instructions ask to change the user's Venmo
  password. One general account-security ICVE machine triggers a Venmo password reset
  through runtime-visible Gmail evidence and reaches 3/3 success with 0 invalid calls and
  0 unsafe state changes. This is a narrow held-out slice, not a full `test_challenge`
  or leaderboard result.
- Held-out AppWorld workout-email Spotify playlist slice:
  `results/appworld_spotify_workout_email_playlist_20260525/20260525_005603` records
  three local `test_challenge` tasks whose public instructions ask to create a Spotify
  playlist from songs sent by a workout partner over email. One general cross-app ICVE
  machine grounds Gmail song evidence, creates the requested Spotify playlist, and
  reaches 3/3 success with 0 invalid calls and 0 unsafe state changes. This is a narrow
  held-out slice, not a full `test_challenge` or leaderboard result.
- Held-out AppWorld phone-message Amazon recommendation purchase slice:
  `results/appworld_amazon_phone_recommendation_purchase_20260525/20260525_011413`
  records three local `test_challenge` tasks whose public instructions ask to buy the
  product recommended by a named contact in a phone message. One general cross-app ICVE
  machine grounds the phone-message evidence, resolves quoted or constrained Amazon
  product candidates, places the bounded order, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Amazon wishlist itemized-text slice:
  `results/appworld_amazon_wishlist_itemized_text_20260525/20260525_045222` records
  three local `test_challenge` tasks whose public instructions ask to text an itemized
  Amazon wishlist cost list to a husband, wife, or partner. One general Amazon + phone
  ICVE machine grounds the relationship through runtime-visible phone contacts, reads
  runtime-visible wishlist names, prices, and quantities, sends the requested
  newline-separated list, and reaches 3/3 success with 0 invalid calls and 0 unsafe
  state changes. This is a narrow held-out slice, not a full `test_challenge` or
  leaderboard result.
- Held-out AppWorld Amazon cart+wishlist total answer slice:
  `results/appworld_amazon_cart_wishlist_total_20260525/20260525_045234` records three
  local `test_challenge` answer-only tasks whose public instructions ask for the total
  cost of the user's Amazon cart and wishlist while ignoring tax and delivery fees. One
  general Amazon ICVE machine sums runtime-visible cart and wishlist item prices times
  quantities and reaches 3/3 success with 0 invalid calls and 0 unsafe state changes.
  This is answer-only coverage evidence, not a full `test_challenge` or leaderboard
  result.
- Held-out AppWorld Amazon wishlist-all order slice:
  `results/appworld_amazon_order_wishlist_all_20260525/20260525_050933` records three
  local `test_challenge` tasks whose public instructions ask to buy every item in the
  runtime-visible Amazon wishlist and ship it to the requested home/work address. One
  general Amazon ICVE machine stages exactly those wishlist items, removes invalid cart
  promo state when visible, places the order through runtime-visible payment cards and
  addresses, and reaches 3/3 success with 0 invalid calls and 0 unsafe state changes.
  This is a narrow held-out slice, not a full `test_challenge` or leaderboard result.
- Held-out AppWorld Amazon cart+wishlist-all order slice:
  `results/appworld_amazon_order_cart_wishlist_all_20260525/20260525_050918` records
  three local `test_challenge` tasks whose public instructions ask to order every item
  in the runtime-visible Amazon cart and wishlist for the requested home/work address.
  The same general Amazon ICVE machine stages both visible collections, clears stale
  promo-code state before checkout when needed, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Amazon recent-order return slice:
  `results/appworld_amazon_return_recent_orders_20260525/20260525_052017` records
  three local `test_challenge` tasks whose public instructions ask to initiate FedEx
  returns for every item in the user's last 2/3/4 Amazon orders. One general Amazon
  ICVE machine sorts runtime-visible orders by creation time, returns the remaining
  unreturned quantity for each order item, and reaches 3/3 success with 0 invalid calls
  and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Amazon last-ordered product question slice:
  `results/appworld_amazon_post_last_order_question_20260525/20260525_052247` records
  three local `test_challenge` tasks whose public instructions ask to post a quoted
  question on the last ordered Amazon t-shirt or sweater. One general Amazon ICVE
  machine scans runtime-visible orders newest-first, resolves the product by requested
  type through visible product metadata, posts the requested question, and reaches 3/3
  success with 0 invalid calls and 0 unsafe state changes. This is a narrow held-out
  slice, not a full `test_challenge` or leaderboard result.
- Held-out AppWorld Amazon last-month review-update slice:
  `results/appworld_amazon_update_last_month_review_20260525/20260525_053844` records
  three local `test_challenge` tasks whose public instructions ask to change the user's
  Amazon review for a requested color and apparel type ordered last calendar month. One
  general Amazon ICVE machine uses runtime-visible order, product, and review APIs to
  identify the existing review and update its rating/title, reaching 3/3 success with
  0 invalid calls and 0 unsafe state changes. This is a narrow held-out slice, not a
  full `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail-to-Spotify song-recommendation reply slice:
  `results/appworld_spotify_liked_song_email_recommendations_20260525/20260525_013420`
  records three local `test_challenge` tasks whose public instructions ask to reply over
  Gmail with liked songs that are also in the Spotify song library. One general cross-app
  ICVE machine grounds the target sender through runtime-visible phone contacts and
  Gmail threads, intersects Spotify liked songs with the song library, replies with the
  requested prefix and comma-separated titles, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Spotify draft recommendation update/send slice:
  `results/appworld_spotify_update_song_recommendation_draft_20260525/20260525_014643`
  records three local `test_challenge` tasks whose public instructions ask to update an
  existing Gmail draft with all liked songs that are also in the user's Spotify song
  library, album library, or playlists, while preserving the draft format and then
  sending it. One general cross-app ICVE machine identifies the target draft, intersects
  Spotify liked songs with the runtime-visible library and playlist evidence, replaces
  only the song-entry block, sends the draft, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Venmo optional-signup payment slice:
  `results/appworld_venmo_optional_signup_payment_20260525/20260525_020403` records
  three local `test_challenge` tasks whose public instructions ask to send money to a
  named Venmo user and say that the current user may need an account first. One general
  ICVE machine performs optional current-user Venmo signup, verifies the account through
  runtime-visible Gmail evidence when needed, grounds the unique named receiver through
  phone contacts and Venmo search, adds a usable payment card if balance is insufficient,
  and reaches 3/3 success with 0 invalid calls and 0 unsafe state changes. This is a
  narrow held-out slice, not a full `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail notification-labeling slice:
  `results/appworld_gmail_label_notification_threads_20260525/20260525_021446` records
  three local `test_challenge` tasks whose public instructions ask to label Gmail inbox
  threads from `notifications@<app>.com` with the corresponding app label while ignoring
  spam and archived threads. One general Gmail ICVE machine enumerates non-spam,
  non-archived inbox threads, grounds notification senders through runtime-visible thread
  details, applies app-derived labels, and reaches 3/3 success with 0 invalid calls and
  0 unsafe state changes. This is a narrow held-out slice, not a full `test_challenge`
  or leaderboard result.
- Held-out AppWorld Gmail priority-relabel slice:
  `results/appworld_gmail_relabel_priority_20260525/20260525_040633` records three
  local `test_challenge` tasks whose public instructions ask to relabel Gmail priority
  threads from one visible label convention to another and remove third-priority labels.
  One general Gmail ICVE machine enumerates runtime-visible labelled threads across
  Gmail categories, applies the requested P1/P2 or priority-1/priority-2 relabels,
  removes the requested third-priority labels, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail archived-thread calendar-delete slice:
  `results/appworld_gmail_delete_archived_window_20260525/20260525_041422` records
  three local `test_challenge` tasks whose public instructions ask to delete archived
  Gmail threads from a calendar-month window. One general Gmail ICVE machine computes
  the requested current/previous-month window from runtime time, collects the full
  archived-thread id set before mutating, deletes only those archived threads, verifies
  the window is empty afterward, and reaches 3/3 success with 0 invalid calls and
  0 unsafe state changes. This is a narrow held-out slice, not a full `test_challenge`
  or leaderboard result.
- Held-out AppWorld Gmail anniversary-announcement forward slice:
  `results/appworld_gmail_forward_anniversary_announcement_20260525/20260525_042330`
  records three local `test_challenge` tasks whose public instructions ask to forward a
  just-sent company anniversary announcement email to a missing coworker, explicitly not
  the whole thread. One general Gmail ICVE machine grounds the sent announcement through
  runtime-visible outbox/thread evidence, selects the matching source email id, forwards
  only that email to the missing recipient, and reaches 3/3 success with 0 invalid calls
  and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail caterer-bill manager-forward slice:
  `results/appworld_gmail_forward_caterer_bill_20260525/20260525_043439` records three
  local `test_challenge` tasks whose public instructions ask to forward a caterer bill
  for a company celebration to the user's manager with a task-specific note prefixed to
  the body. One general Gmail + phone ICVE machine grounds the manager through
  runtime-visible phone contacts, selects the matching incoming bill email and attachment
  through runtime-visible Gmail thread evidence, drafts a forward, prefixes the requested
  note to the draft body, sends it, and reaches 3/3 success with 0 invalid calls and
  0 unsafe state changes. This is a narrow held-out slice, not a full `test_challenge`
  or leaderboard result.
- Held-out AppWorld Gmail weekly-manager-task reply slice:
  `results/appworld_gmail_weekly_manager_tasks_20260525/20260525_044411` records three
  local `test_challenge` tasks whose public instructions ask to close out weekly
  manager-assigned Gmail task threads by replying with one of two status messages based
  on whether each task thread was starred, then unstar only those task threads. One
  general Gmail + phone ICVE machine grounds the manager through runtime-visible phone
  contacts, filters this week's task threads by sender and subject prefix, replies
  according to the initial starred state, unstars only completed task threads, and
  reaches 3/3 success with 0 invalid calls and 0 unsafe state changes. This is a narrow
  held-out slice, not a full `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail scheduled-draft send-now slice:
  `results/appworld_gmail_send_scheduled_now_20260525/20260525_034758` records three
  local `test_challenge` tasks whose public instructions ask to send all
  future-scheduled Gmail messages immediately. One general Gmail ICVE machine enumerates
  runtime-visible scheduled drafts, sends each draft right away, verifies that no
  scheduled drafts remain, and reaches 3/3 success with 0 invalid calls and 0 unsafe
  state changes. This is a narrow held-out slice, not a full `test_challenge` or
  leaderboard result.
- Held-out AppWorld Gmail read-state calendar-window slice:
  `results/appworld_gmail_mark_read_state_20260525/20260525_035609` records three local
  `test_challenge` tasks whose public instructions ask to mark inbox/outbox Gmail
  threads read or unread within a calendar-month/year window. One general Gmail ICVE
  machine computes the calendar window from runtime time, enumerates inbox and outbox
  threads, changes only mismatched read states, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail job-search attachment/send slice:
  `results/appworld_gmail_job_search_attach_send_20260525/20260525_023325` records
  three local `test_challenge` tasks whose public instructions ask to attach a freshly
  updated `resume.pdf` or `cv.pdf` from the file system to recent job-search Gmail
  drafts, replacing stale attachments if present, and then send the drafts. One general
  Gmail + file-system ICVE machine selects the non-trash, most recently updated matching
  PDF through runtime-visible file metadata, filters recent job-application drafts, adds
  or overwrites the attachment, sends the drafts, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail flight-ticket download slice:
  `results/appworld_gmail_flight_ticket_download_20260525/20260525_033611` records
  three local `test_challenge` tasks whose public instructions ask to download the
  ticket attachment for a weekend flight to a specified destination into a requested
  local directory. One general Gmail + file-system ICVE machine grounds flight evidence
  through runtime-visible Gmail threads, selects ticket rather than receipt attachments,
  writes the file to the requested directory, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld Gmail-receipt Venmo payment slice:
  `results/appworld_venmo_flight_bill_email_20260525/20260525_025233` records three
  local `test_challenge` tasks whose public instructions ask to pay a named contact's
  emailed flight bill on Venmo with a specified description note. One general Gmail +
  file-system + Venmo ICVE machine grounds the contact through runtime-visible phone
  records, downloads the Gmail receipt attachment, extracts the owed amount from the
  receipt content, resolves the Venmo receiver, and reaches 3/3 success with 0 invalid
  calls and 0 unsafe state changes. This is a narrow held-out slice, not a full
  `test_challenge` or leaderboard result.
- Held-out AppWorld coworker Venmo gift + email slice:
  `results/appworld_venmo_coworker_sprint_gifts_20260525/20260525_030821` records three
  local `test_challenge` tasks whose public instructions ask to privately pay every
  coworker a sprint gift on Venmo and then send one Gmail message to all of them. One
  general Venmo + Gmail ICVE machine grounds coworker contacts through runtime-visible
  phone records, verifies each Venmo receiver, funds the total payment when needed, sends
  private transactions, and sends the requested group email, reaching 3/3 success with
  0 invalid calls and 0 unsafe state changes. This is a narrow held-out slice, not a
  full `test_challenge` or leaderboard result.
- Held-out AppWorld shared-subscription password + phone-text slice:
  `results/appworld_shared_subscription_password_text_20260525/20260525_032327` records
  three local `test_challenge` tasks whose public instructions ask to change a shared
  Amazon Prime or Spotify Premium account password and notify roommates or siblings by
  phone text. One general Amazon/Spotify + Gmail + phone ICVE machine requests a
  password-reset code for the target app, grounds the code through runtime-visible Gmail
  evidence, resets the account password, and sends the new password to all target
  relationship contacts, reaching 3/3 success with 0 invalid calls and 0 unsafe state
  changes. This is a narrow held-out slice, not a full `test_challenge` or leaderboard
  result.
- Multi-turn diagnostic:
  `results/toolsandbox_qwen25_05b_rave2_multiturn_completion_patch_full/20260504_131011`
  and hosted replication
  `results/frontier_toolsandbox_replication_deepseek/deepseek-chat_multiturn_hidden_completion_patch2/20260504_130748`
- Active targeted public AppWorld deterministic 72-task slice:
  `results/appworld_rave_slice_expanded72/20260506_000919`
- Active targeted public AppWorld Qwen2.5-3B intent-extraction 72-task slice:
  `results/appworld_rave_slice_llm_intent_qwen25_3b_expanded72/20260506_001050`
- Active targeted public AppWorld DeepSeek-chat intent-extraction 72-task combined slice:
  `results/appworld_rave_slice_llm_intent_deepseek_chat_combined72/20260506_003007`
- Active targeted public AppWorld DeepSeek-reasoner intent-extraction 72-task combined
  slice:
  `results/appworld_rave_slice_llm_intent_deepseek_reasoner_combined72/20260506_003123`
- Active targeted public AppWorld Qwen2.5-3B direct-code / typed-intent-code /
  code-repair / multi-step code-observation 72-task baselines:
  `results/appworld_llm_direct_code_qwen25_3b_combined72/20260506_001800`,
  `results/appworld_llm_intent_code_qwen25_3b_combined72/20260506_001800`,
  `results/appworld_llm_code_repair_qwen25_3b_combined72/20260506_001800`, and
  `results/appworld_llm_react_code_qwen25_3b_combined72/20260506_001800`
- Active targeted public AppWorld DeepSeek-chat direct-code / typed-intent-code /
  code-repair / multi-step code-observation 72-task baselines:
  `results/appworld_llm_direct_code_deepseek_chat_combined72/20260506_003508`,
  `results/appworld_llm_intent_code_deepseek_chat_combined72/20260506_003733`,
  `results/appworld_llm_code_repair_deepseek_chat_combined72/20260506_003945`, and
  `results/appworld_llm_react_code_deepseek_chat_combined72/20260506_004300`
- Current AppWorld summary note:
  `results/appworld_expanded72_20260506.md`
- Historical targeted public AppWorld 66-task note and rows:
  `results/appworld_rave_slice_20260504.md`,
  `results/appworld_rave_slice_expanded66/20260505_063044`,
  `results/appworld_rave_slice_llm_intent_qwen25_3b_expanded66/20260505_063133`,
  `results/appworld_rave_slice_llm_intent_deepseek_chat_expanded66/20260505_063312`,
  `results/appworld_rave_slice_llm_intent_deepseek_reasoner_expanded66/20260505_063509`,
  `results/appworld_llm_direct_code_expanded66/20260505_063829`,
  `results/appworld_llm_intent_code_expanded66/20260505_064515`,
  `results/appworld_llm_code_repair_deepseek_chat_combined66/20260505_143100`, and
  `results/appworld_llm_react_code_deepseek_chat_combined66/20260505_143100`
- Targeted public AppWorld playlist-sharing smoke tests:
  `results/appworld_rave_slice_share_playlist_smoke/20260505_063030`,
  `results/appworld_llm_direct_code_qwen_share_playlist_smoke/20260505_071918`,
  `results/appworld_llm_intent_code_qwen_share_playlist_smoke/20260505_071948`,
  `results/appworld_llm_react_code_qwen_share_playlist_smoke/20260505_072016`,
  `results/appworld_llm_code_repair_qwen_share_playlist_smoke/20260505_072057`,
  `results/appworld_llm_direct_code_deepseek_reasoner_share_playlist_smoke/20260505_082154`,
  `results/appworld_llm_intent_code_deepseek_reasoner_share_playlist_smoke/20260505_082245`,
  `results/appworld_llm_code_repair_deepseek_chat_share_playlist_smoke/20260505_082511`,
  and `results/appworld_llm_react_code_deepseek_chat_share_playlist_smoke/20260505_082721`
- Targeted public AppWorld hosted DeepSeek-chat incremental six-task repair/ReAct slices:
  `results/appworld_llm_code_repair_deepseek_chat_incremental6/20260505_083339`
  and `results/appworld_llm_react_code_deepseek_chat_incremental6/20260505_083153`
- Targeted public AppWorld hosted DeepSeek-chat incremental twelve-task repair/ReAct slices:
  `results/appworld_llm_code_repair_deepseek_chat_incremental12/20260505_083849`
  and `results/appworld_llm_react_code_deepseek_chat_incremental12/20260505_084238`
- AppWorld runner incremental-output regression:
  `results/appworld_runner_incremental_smoke/20260505_083105`
- AppWorld packaged-evaluator reports for the historical 66-task slice:
  `results/appworld_official_evaluator_rave_expanded66_20260505.md`, with detailed
  reports under `experiments/outputs/*/evaluations/rave_expanded66.{json,txt}`
- AppWorld packaged-evaluator reports for the active 72-task slice:
  `results/appworld_expanded72_20260506.md`, with detailed reports under
  `experiments/outputs/*/evaluations/rave_expanded72.{json,txt}`
- Official AppWorld repository agent-runner attempt, one-task smoke, and dev10 slices:
  `results/appworld_official_agent_attempt_20260505.md` and
  `results/appworld_official_runner_smoke_20260506.md` and
  `results/appworld_official_runner_dev10_20260506.md` and
  `results/appworld_official_runner_dev10_full50_20260506.md`. The latest
  `appworld-agents` runner imports, the Git LFS bundle blocker is resolved, the
  constrained 3-step DeepSeek `simplified_react_code_agent` check is retained as smoke
  evidence, and the default 50-step official DeepSeek ReAct-code baseline reaches
  90.0 task-goal / 75.0 scenario-goal completion on `dev10_full50`. RAVE deterministic
  and RAVE + DeepSeek-chat intent extraction both reach 100.0 / 100.0 on the same small
  official AppWorld 0.2.0 slice after four additional intent machines are registered.
  Do not claim leaderboard-agent benchmark coverage from this small slice.
- Complete local official AppWorld 0.2.0 dev split with RAVE rows:
  `results/appworld_official_runner_dev57_20260506.md`,
  `results/appworld_rave_official_dev57_final/20260506_021705`, and
  `results/appworld_rave_official_dev57_final_llm_intent_deepseek_chat/20260506_021940`.
  AppWorld's packaged evaluator reports 100.0 task-goal / 100.0 scenario-goal completion
  for deterministic RAVE and RAVE + DeepSeek-chat intent extraction on all 57 official
  dev tasks. Local logs report 57/57 success, 0 unsafe state changes per task, and
  0.0351 invalid API attempts per task. The same record also includes the official
  DeepSeek `simplified_react_code_agent` default-50-step baseline on the same 57 tasks:
  79.0 task-goal / 73.7 scenario-goal, 45/57 task-level success, 879 LLM calls,
  6,452,544 tokens, and estimated cost 0.413653436. This is local official dev coverage,
  not held-out test or leaderboard coverage.
- Held-out AppWorld test-normal smoke:
  `results/appworld_test_normal_smoke12_20260506.md` and
  `results/appworld_test_normal_smoke60_20260506.md`. The initial coverage check under
  `results/appworld_rave_official_test_normal_smoke12/20260506_040346` had
  supported_rate 0.0 and success_rate 0.0. After registering additional
  `IntentMachine`s, the first-12 row under
  `results/appworld_rave_official_test_normal_smoke12_expanded_v2/20260506_041455`
  reaches 12/12 success with 0 invalid tool calls and 0 unsafe state changes. The
  expanded first-60 row under
  `results/appworld_rave_official_test_normal_smoke60_expanded_v2/20260506_042801`
  reaches 38/60 overall success, 39/60 supported, 38/39 supported success, 0 unsafe
  state changes, and 0.35 invalid abstentions per task. This is held-out smoke evidence
  only, not a full test split or leaderboard run.
  The larger first-120 deterministic smoke is summarized in
  `results/appworld_test_normal_smoke120_20260506.md`, with raw output under
  `results/appworld_rave_official_test_normal_smoke120_d18139b_card_path_v67/20260507_030820`;
  it reaches 117/120 overall success, 117/120 supported, 117/117 supported success, 0
  unsafe state changes, and 0.0250 invalid/tool per task after adding five Simple Note,
  six Venmo, one Simple Note-to-Spotify playlist, one Simple Note liked-song
  release-month, one reunion RSVP file-update, and one phone-sourced Spotify playlist
  update `IntentMachine`, one roommate dinner settlement `IntentMachine`, plus one offline Spotify playback `IntentMachine`. The invalid count consists of 3 unsupported/no-action abstentions from the unsupported vacation-settlement family. The named-payment card-refill probe was replaced by a no-failed-call public-card add path, and the roommate request-approval card path now rotates successful cards to avoid reusing a depleted card first. The dedicated 3-task birthday child payment smoke under
  `results/appworld_rave_official_test_normal_270f1ff_birthday_v26/20260506_121530`
  reaches 3/3 success, 0 unsafe state changes, and 0 invalid tool calls. The dedicated
  3-task sent-request correction smoke under
  `results/appworld_rave_official_test_normal_90adc3f_sent_request_correction_v32/20260506_123327`
  reaches 3/3 success, 0 unsafe state changes, and 0 invalid tool calls. The dedicated
  3-task reunion RSVP file-update smoke under
  `results/appworld_rave_official_test_normal_b9c5c9a_reunion_rsvp_v36/20260506_130212`
  reaches 3/3 success, 0 unsafe state changes, and 0 invalid tool calls. The dedicated
  3-task phone playlist suggestion smoke under
  `results/appworld_rave_official_test_normal_042a9fc_phone_playlist_v42/20260506_132749`
  reaches 3/3 success, 0 unsafe state changes, and 0 invalid tool calls. The dedicated
  3-task roommate dinner settlement smoke under
  `results/appworld_rave_official_test_normal_2d9f728_roommate_dinner_v46/20260506_134252`
  reaches 3/3 success, 0 unsafe state changes, and 0 invalid tool calls. The dedicated
  15-task Simple Note gap smoke under
  `results/appworld_rave_official_test_normal_simple_note_gap15_smoke_v2/20260506_071635`
  reaches 18/18 success, 0 unsafe state changes, and 0 invalid tool calls.
  `results/appworld_rave_official_test_normal_smoke60_llm_intent_deepseek_chat/20260506_043113`
  records DeepSeek-chat intent extraction on the same 60 tasks: 38/60 success, 0 unsafe
  state changes, and 1 LLM call per task. The follow-up guard smoke
  `results/appworld_rave_official_test_normal_housing_guard_deepseek/20260506_043304`
  verifies that unsupported housing-bill correction tasks now abstain rather than
  over-generalizing to the generic Venmo pending-request machine.
  `results/appworld_rave_official_test_normal_smoke120_llm_intent_deepseek_chat/20260506_044117`
  records DeepSeek-chat intent extraction on the same first 120 tasks before the latest
  guard patch: 65/120 overall success, 71/120 supported, 65/71 supported success,
  0 unsafe state changes, 0.4083 invalid abstentions per task, and 1 LLM call per task.
  The five extra supported failures are LLM over-generalizations on unsupported offline
  Spotify playback and named carpool Venmo request tasks. The follow-up guard smoke
  `results/appworld_rave_official_test_normal_llm_guard_deepseek_0de03ea_9ef798c/20260506_044730`
  verifies that all six `0de03ea`/`9ef798c` variants now abstain with 0 unsafe state
  changes.
  The latest full first-120 DeepSeek-chat rerun under
  `results/appworld_rave_official_test_normal_smoke120_llm_intent_deepseek_chat_d18139b_card_path_v68/20260507_031027`
  reports 117/120 overall success, 117/120 supported, 117/117 supported success, 0 unsafe
  state changes, 0.0250 invalid/tool per task, and 1 LLM call per task. The strict
  verifier blocks unsupported `3b8fb7a` vacation-settlement tasks before code execution
  and counts them as invalid no-action results.
  The dedicated DeepSeek-chat
  birthday child payment smoke under
  `results/appworld_rave_official_test_normal_270f1ff_birthday_llm_intent_deepseek_v27/20260506_121544`
  reports 3/3 success, 0 unsafe state changes, 0 invalid tool calls, and 1 LLM call per
  task. The dedicated DeepSeek-chat sent-request correction smoke under
  `results/appworld_rave_official_test_normal_90adc3f_sent_request_correction_llm_intent_deepseek_v33/20260506_123342`
  reports 3/3 success, 0 unsafe state changes, 0 invalid tool calls, and 1 LLM call per
  task. The dedicated DeepSeek-chat reunion RSVP file-update smoke under
  `results/appworld_rave_official_test_normal_b9c5c9a_reunion_rsvp_llm_intent_deepseek_v37/20260506_130228`
  reports 3/3 success, 0 unsafe state changes, 0 invalid tool calls, and 1 LLM call per
  task. The dedicated DeepSeek-chat phone playlist suggestion smoke under
  `results/appworld_rave_official_test_normal_042a9fc_phone_playlist_llm_intent_deepseek_v43/20260506_132808`
  reports 3/3 success, 0 unsafe state changes, 0 invalid tool calls, and 1 LLM call per
  task. The dedicated DeepSeek-chat roommate dinner settlement smoke under
  `results/appworld_rave_official_test_normal_2d9f728_roommate_dinner_llm_intent_deepseek_v47/20260506_134307`
  reports 3/3 success, 0 unsafe state changes, 0 invalid tool calls, and 1 LLM call per
  task. The dedicated DeepSeek-chat
  Simple Note bucket-count smoke under
  `results/appworld_rave_official_test_normal_simple_note_bucket_count_llm_intent_deepseek_chat_smoke/20260506_072157`
  reports 3/3 success, 0 unsafe state changes, 0 invalid tool calls, and 1 LLM call per
  task.
- Held-out AppWorld test-normal file-level continuation:
  After the first-120 smoke, the file-level rerun over the actual remaining local
  `test_normal.txt` entries under
  `results/appworld_rave_official_test_normal_smoke121_167_d18139b_card_path_v69/20260507_032529`
  and
  `results/appworld_rave_official_test_normal_smoke121_167_llm_intent_deepseek_chat_d18139b_card_path_v70/20260507_032651`
  reaches 47/47 for deterministic and DeepSeek-chat intent rows with 0 invalid and
  0 unsafe state changes. The final local no-newline task ID is recorded under
  `results/appworld_rave_official_test_normal_missing_bde252e3_20260524/20260524_215549`.
  The superseded deterministic combined local file-level summary under
  `results/appworld_rave_official_test_normal_full168_d18139b_card_path_20260524/`
  reports 165/168 overall success and left the three `3b8fb7a` trip-note debt tasks as
  unsupported no-action outcomes. The follow-up general machine for Simple Note trip-debt
  ledgers to private Venmo payments/requests is validated on
  `results/appworld_trip_note_debts_20260524/20260524_225607` with 3/3 success, 0
  invalid calls, and 0 unsafe state changes. The current deterministic combined local
  file-level summary under
  `results/appworld_rave_official_test_normal_full168_trip_note_debts_20260524/20260524_225648`
  reports 168/168 overall success, 168/168 supported-task success, 0 unsafe state
  changes, and 0 invalid/tool per task. This is local AppWorld 0.2.0 file-level evidence,
  not a public leaderboard submission.
- Held-out AppWorld test-challenge Amazon-prefix diagnostic:
  `results/20260507_035124` records the first 24 `test_challenge` ids before the latest
  saved-list Amazon machines at 3/24 success, 3/24 supported, 0 unsafe state changes,
  and 0.8750 invalid/tool per task. After adding conservative machines for moving
  already-grounded product types between cart/wish list and ordering already-grounded
  product types from cart/wish list, `results/20260507_040059` reaches 12/24 success,
  12/24 supported, 0 unsafe state changes, and 0.5000 invalid/tool per task. The
  remaining unsupported tasks are product-search purchases that require selecting among
  sellers, dimensions, ratings, or multiple candidate products. This diagnostic is not a
  full `test_challenge` split or leaderboard result.
  The dedicated refill-family
  smoke under
  `results/appworld_rave_official_test_normal_venmo_relationship_refill_smoke/20260506_051858`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; the dedicated
  Simple Note habit-streak smoke under
  `results/appworld_rave_official_test_normal_simple_note_habit_streak_smoke/20260506_052539`
  also reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; the
  dedicated monthly Venmo expense-log smoke under
  `results/appworld_rave_official_test_normal_simple_note_monthly_venmo_expense_smoke/20260506_053218`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; the dedicated
  favorite-recipe reply smoke under
  `results/appworld_rave_official_test_normal_phone_favorite_recipe_reply_smoke/20260506_053548`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; the dedicated
  Splitwise phone-invitation smoke under
  `results/appworld_rave_official_test_normal_splitwise_phone_invites_smoke/20260506_054327`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_splitwise_phone_invites_llm_intent_deepseek_chat_smoke/20260506_054556`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes; the dedicated Venmo signup/Phone notification smoke under
  `results/appworld_rave_official_test_normal_venmo_signup_contacts_smoke/20260506_054845`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_venmo_signup_contacts_llm_intent_deepseek_chat_smoke/20260506_054857`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes; the dedicated Todoist reassignment smoke under
  `results/appworld_rave_official_test_normal_todoist_reassign_smoke_v2/20260506_055552`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_todoist_reassign_llm_intent_deepseek_chat_smoke/20260506_055608`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes; the dedicated Splitwise/Venmo receipt-payment smoke under
  `results/appworld_rave_official_test_normal_splitwise_venmo_receipts_smoke/20260506_060608`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_splitwise_venmo_receipts_llm_intent_deepseek_chat_smoke/20260506_060625`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes; the dedicated Simple Note/Splitwise trip-expense smoke under
  `results/appworld_rave_official_test_normal_splitwise_trip_expenses_smoke_v4/20260506_061535`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_splitwise_trip_expenses_llm_intent_deepseek_chat_smoke/20260506_061613`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes; the dedicated Todoist/Spotify playlist-suggestion smoke under
  `results/appworld_rave_official_test_normal_todoist_spotify_playlist_smoke/20260506_062627`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_todoist_spotify_playlist_llm_intent_deepseek_chat_smoke/20260506_062642`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes; the dedicated CSV debt-payment smoke under
  `results/appworld_rave_official_test_normal_csv_debts_smoke_v3/20260506_063851`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_csv_debts_llm_intent_deepseek_chat_smoke/20260506_063921`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes; the dedicated Todoist/SimpleNote schedule-fill smoke under
  `results/appworld_rave_official_test_normal_todoist_schedule_fill_smoke_v2/20260506_065238`
  reports 3/3 success, 0 invalid tool calls, and 0 unsafe state changes; and the
  DeepSeek-chat intent-extraction smoke for the same family under
  `results/appworld_rave_official_test_normal_todoist_schedule_fill_llm_intent_deepseek_chat_smoke_v2/20260506_065410`
  reports 3/3 success, 1 LLM call per task, 0 invalid tool calls, and 0 unsafe state
  changes. This is continuation coverage evidence and is not used as a headline claim;
  the full held-out test split and public leaderboard remain out of scope.
- Historical targeted public AppWorld DeepSeek code-repair baseline on the preceding
  63-task slice:
  `results/appworld_llm_code_repair_expanded63/20260505_055055`
- Historical targeted public AppWorld DeepSeek multi-step code-observation baseline on
  the preceding 63-task slice:
  `results/appworld_llm_react_code_expanded63/20260505_060421`

## Derived Summaries

```bash
<CONDA_ROOT>/bin/conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/summarize_rave2_statistics.py
```

Output:

- `results/statistical_intervals_20260504.md`

The hosted AppWorld DeepSeek-chat repair and multi-step code-observation baselines were
first combined into historical 66-task rows from incrementally flushed shards, then
extended to the active 72-task rows with the final six Spotify-family tasks. Duplicate
`task_id`s are rejected:

```bash
APPWORLD_ROOT=<PROJECT_ROOT> \
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld/bin/python \
  experiments/combine_appworld_slices.py \
  --inputs \
    results/appworld_llm_code_repair_deepseek_chat_incremental12_first/20260505_084633/episode_metrics.csv \
    results/appworld_llm_code_repair_deepseek_chat_incremental12_middle1/20260505_140750/episode_metrics.csv \
    results/appworld_llm_code_repair_deepseek_chat_incremental12_middle2/20260505_141415/episode_metrics.csv \
    results/appworld_llm_code_repair_deepseek_chat_incremental12_middle3/20260505_141954/episode_metrics.csv \
    results/appworld_llm_code_repair_deepseek_chat_incremental6_missing/20260505_142751/episode_metrics.csv \
    results/appworld_llm_code_repair_deepseek_chat_incremental12/20260505_083849/episode_metrics.csv \
  --output-dir results/appworld_llm_code_repair_deepseek_chat_combined66/20260505_143100 \
  --method appworld_llm_code_repair_slice \
  --experiment-name appworld_code_repair_deepseek_chat_combined66
```

```bash
APPWORLD_ROOT=<PROJECT_ROOT> \
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld/bin/python \
  experiments/combine_appworld_slices.py \
  --inputs \
    results/appworld_llm_react_code_deepseek_chat_incremental12_first/20260505_140448/episode_metrics.csv \
    results/appworld_llm_react_code_deepseek_chat_incremental12_middle1/20260505_141040/episode_metrics.csv \
    results/appworld_llm_react_code_deepseek_chat_incremental12_middle2/20260505_141642/episode_metrics.csv \
    results/appworld_llm_react_code_deepseek_chat_incremental12_middle3/20260505_142349/episode_metrics.csv \
    results/appworld_llm_react_code_deepseek_chat_incremental6_missing/20260505_142938/episode_metrics.csv \
    results/appworld_llm_react_code_deepseek_chat_incremental12/20260505_084238/episode_metrics.csv \
  --output-dir results/appworld_llm_react_code_deepseek_chat_combined66/20260505_143100 \
  --method appworld_llm_react_code_slice \
  --experiment-name appworld_react_code_deepseek_chat_combined66
```

The active 72-task metric rows are then produced with:

```bash
APPWORLD_ROOT=<PROJECT_ROOT> \
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld/bin/python \
  experiments/combine_appworld_slices.py \
  --inputs \
    results/appworld_llm_code_repair_deepseek_chat_combined66/20260505_143100/episode_metrics.csv \
    results/appworld_llm_code_repair_deepseek_chat_incremental6_to72/20260506_003743/episode_metrics.csv \
  --output-dir results/appworld_llm_code_repair_deepseek_chat_combined72/20260506_003945 \
  --method appworld_llm_code_repair_slice \
  --experiment-name appworld_code_repair_deepseek_chat_combined72
```

```bash
APPWORLD_ROOT=<PROJECT_ROOT> \
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld/bin/python \
  experiments/combine_appworld_slices.py \
  --inputs \
    results/appworld_llm_react_code_deepseek_chat_combined66/20260505_143100/episode_metrics.csv \
    results/appworld_llm_react_code_deepseek_chat_incremental6_to72/20260506_004012/episode_metrics.csv \
  --output-dir results/appworld_llm_react_code_deepseek_chat_combined72/20260506_004300 \
  --method appworld_llm_react_code_slice \
  --experiment-name appworld_react_code_deepseek_chat_combined72
```

The active AppWorld packaged-evaluator checks use:

```bash
<CONDA_ROOT>/envs/pctu-appworld/bin/python \
  experiments/combine_appworld_output_tasks.py \
  --inputs \
    experiments/outputs/appworld_code_repair_deepseek_chat_combined66 \
    experiments/outputs/appworld_code_repair_deepseek_chat_incremental6_to72 \
  --output-dir experiments/outputs/appworld_code_repair_deepseek_chat_combined72
```

```bash
<CONDA_ROOT>/envs/pctu-appworld/bin/python \
  experiments/combine_appworld_output_tasks.py \
  --inputs \
    experiments/outputs/appworld_react_code_deepseek_chat_combined66 \
    experiments/outputs/appworld_react_code_deepseek_chat_incremental6_to72 \
  --output-dir experiments/outputs/appworld_react_code_deepseek_chat_combined72
```

```bash
APPWORLD_ROOT=<PROJECT_ROOT> \
<CONDA_ROOT>/envs/pctu-appworld/bin/python -m appworld.cli evaluate \
  rave_appworld_expanded72 rave_expanded72 \
  --root <PROJECT_ROOT>
```

Run the same command with `rave_appworld_qwen25_3b_intent_expanded72`,
`rave_appworld_deepseek_chat_intent_combined72`,
`rave_appworld_deepseek_reasoner_intent_combined72`,
`appworld_direct_code_qwen25_3b_combined72`,
`appworld_intent_code_qwen25_3b_combined72`,
`appworld_code_repair_qwen25_3b_combined72`,
`appworld_react_code_qwen25_3b_combined72`,
`appworld_direct_code_deepseek_chat_combined72`,
`appworld_intent_code_deepseek_chat_combined72`,
`appworld_code_repair_deepseek_chat_combined72`, and
`appworld_react_code_deepseek_chat_combined72` to reproduce the active evaluator reports
summarized in `results/appworld_expanded72_20260506.md`.

The complete local official AppWorld dev57 evaluator checks use:

```bash
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
PYTHONPATH=<PROJECT_ROOT>/src \
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python -m appworld.cli evaluate \
  rave_official_dev57_final dev \
  --root <PROJECT_ROOT>/appworld_020_root
```

Run the same command with
`rave_official_dev57_final_llm_intent_deepseek_chat` to reproduce the DeepSeek-chat
intent-extraction evaluator report. The same-split official ReAct-code row uses
`appworld run auto` with dataset `dev57_full50`; see
`results/appworld_official_runner_dev57_20260506.md` for the exact command and output
paths.

## Verification Commands

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python -m py_compile \
  experiments/summarize_rave2_statistics.py \
  experiments/summarize_icve_review_strengthening.py \
  experiments/run_dynamic_synthesis_probe.py \
  experiments/test_dynamic_machine_synthesis.py \
  src/pctu_pilot/rave_dsl.py \
  src/pctu_pilot/rave_runtime.py \
  src/pctu_pilot/appworld_agents.py \
  src/pctu_pilot/toolsandbox_agents.py \
  src/pctu_pilot/__init__.py
```

```bash
APPWORLD_ROOT=<PROJECT_ROOT> \
<CONDA_ROOT>/envs/pctu-appworld/bin/python -m py_compile \
  experiments/run_appworld_rave_slice.py \
  src/pctu_pilot/appworld_agents.py
```

```bash
set -a
source experiments/deepseek_replication.env
set +a
APPWORLD_ROOT=<PROJECT_ROOT> \
PYTHONPATH=<PROJECT_ROOT>/src \
<CONDA_ROOT>/envs/pctu-appworld/bin/python \
  experiments/run_appworld_rave_slice.py \
  --agent llm-intent
```

```bash
cd paper
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  tectonic --keep-logs --keep-intermediates rave_intent_compiled_verified_execution_arr.tex
```

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/test_dynamic_machine_synthesis.py
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/run_dynamic_synthesis_probe.py
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/run_dynamic_affordance_generalization.py
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/summarize_icve_review_strengthening.py
```

## Scope Boundaries

Current claims should be limited to:

- public ToolSandbox no-distraction single-turn and insufficient-information suites,
- targeted public AppWorld stateful slice evidence, including local Qwen2.5-3B and
  hosted DeepSeek intent extraction plus direct-code, typed-intent-code, code-repair, and
  multi-step code-observation baselines on the same 72-task dataset; all are labeled as
  slices rather than a full leaderboard run,
- complete local official AppWorld 0.2.0 dev57 RAVE rows for deterministic typed
  compilers and DeepSeek-chat intent extraction, both evaluated with AppWorld's packaged
  evaluator, plus same-split local official DeepSeek ReAct-code comparison,
- local Qwen2.5 model scales, a small Phi-3-mini diagnostic, and hosted
  DeepSeek-chat/DeepSeek-reasoner replications,
- covered high-risk intents registered as ICVE machines.
- the dynamic-synthesis and affordance-template induction probes only for regular
  ToolSandbox-style boolean setting APIs, where candidates pass shadow-mode, invariant,
  and counterexample checks before promotion.

Current claims should **not** include:

- broad multi-turn stateful tool-use success,
- broad proprietary frontier-model coverage,
- full AppWorld held-out test or leaderboard coverage,
- public leaderboard-agent comparisons beyond the local official dev57 split,
- safety for arbitrary tools outside the registered intent machines.
- automatic synthesis of AppWorld purchase, Gmail, vacation-expense, or other multi-entity
  state machines.

The current frontier/OpenAI-compatible replication template is:

```bash
FRONTIER_BASE_URL=https://api.example.com/v1 \
FRONTIER_MODEL=frontier-model-name \
FRONTIER_API_KEY=... \
MAX_SCENARIOS=0 \
./experiments/run_frontier_toolsandbox_replication.sh
```

For DeepSeek specifically, use:

```bash
cp experiments/deepseek_replication.env.example experiments/deepseek_replication.env
# edit experiments/deepseek_replication.env and fill FRONTIER_API_KEY
source experiments/deepseek_replication.env
./experiments/run_frontier_toolsandbox_replication.sh
```
