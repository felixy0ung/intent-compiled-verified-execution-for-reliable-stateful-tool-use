# Intent-Compiled Verified Execution

This repository contains the code and summary artifacts for **Intent-Compiled Verified
Execution (ICVE)**, a runtime-checked approach for reliable stateful tool use.

Some package names and historical paths still use `pctu_pilot`, `RAVE`, or `RAVE-2`.
The method name used in the paper is ICVE.

## Overview

Stateful tool agents often fail because one free-form model loop is asked to perform
intent recognition, evidence search, argument grounding, precondition repair, mutation,
and stopping. ICVE moves covered high-risk intents into typed `IntentMachine`s. Each
machine has a schema, compiler, and handler; the runtime owns evidence acquisition,
precondition checks, repair, abstention, execution, and postcondition stopping.

The current claim is intentionally bounded: ICVE improves safety and efficiency for
registered stateful task families and for a small class of signature-identifiable boolean
setting APIs. It is not an open-domain tool-use safety guarantee and it is not a public
AppWorld leaderboard submission.

## Main Results Snapshot

- ToolSandbox single-turn and insufficient-information suites: ICVE reduces invalid and
  unsafe calls to zero on covered mutating tasks while using far fewer model calls/tokens
  than ReAct.
- Model checks: local Qwen2.5-0.5B, Qwen2.5-3B, Qwen2.5-7B-4bit, a Phi-3-mini
  diagnostic, and hosted DeepSeek-chat / DeepSeek-reasoner replications.
- Guardrail diagnostic: ReAct+schema/proof/verifier improves safety but still leaves
  model-owned proof/action retry loops; ICVE removes the mutating loop for covered
  intents.
- AppWorld targeted 72-task slice: deterministic ICVE and real-LLM intent extraction
  rows reach 72/72, while direct-code and typed-intent-code baselines remain much lower.
- AppWorld local official dev57: deterministic ICVE and ICVE + DeepSeek-chat intent
  extraction reach 100.0 task-goal / 100.0 scenario-goal with AppWorld's packaged
  evaluator on the same local dev split.
- AppWorld local `test_normal.txt` diagnostic: deterministic ICVE now supports and
  solves 168/168 tasks with 0 invalid calls and 0 unsafe state changes.
- Static public-instruction coverage audit: the registry compiles 168/168 local
  `test_normal.txt` instructions and 111/417 local `test_challenge.txt` instructions.
  The remaining `test_challenge` buckets are reported as coverage gaps, not successes.
- Held-out AppWorld phone-message account-verification slice: one general machine covers
  3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld Gmail relation-star slice: one general machine covers 3
  `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld expired-payment-card cleanup slice: one general cross-app machine
  covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld Venmo password-reset slice: one general account-security machine
  covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld workout-email Spotify playlist slice: one general cross-app machine
  covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld phone-message Amazon recommendation purchase slice: one general
  cross-app machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls,
  and 0 unsafe changes.
- Held-out AppWorld Amazon wishlist itemized-text slice: one general Amazon + phone
  machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld Amazon cart+wishlist total answer slice: one general Amazon machine
  covers 3 `test_challenge` answer-only tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld Amazon saved-collections order slices: one general Amazon machine
  covers wishlist-only and cart+wishlist purchase templates across 6 `test_challenge`
  tasks with 6/6 success, 0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld Amazon recent-order return slice: one general Amazon machine covers
  return requests for all items in the last 2/3/4 orders across 3 `test_challenge`
  tasks with 3/3 success, 0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld Amazon last-ordered product question slice: one general Amazon
  machine posts the requested question on the last ordered product of the requested type
  across 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld Amazon last-month review-update slice: one general Amazon machine
  updates the existing review for the requested color and apparel type across 3
  `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld Amazon last-order question-answer slice: one general Amazon
  answer-only machine resolves the user's latest matching product question and answers
  yes/no from visible answers across 3 `test_challenge` tasks with 3/3 success,
  0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld Gmail-to-Spotify song-recommendation reply slice: one general
  cross-app machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls,
  and 0 unsafe changes.
- Held-out AppWorld Spotify draft recommendation update/send slice: one general cross-app
  machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld Venmo optional-signup payment slice: one general payment machine
  covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld Gmail notification-labeling slice: one general Gmail machine covers
  3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld Gmail priority-relabel slice: one general Gmail machine covers
  3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe changes.
- Held-out AppWorld Gmail archived-thread calendar-delete slice: one general Gmail
  machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld Gmail anniversary-announcement forward slice: one general Gmail
  machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld Gmail caterer-bill manager-forward slice: one general Gmail +
  phone machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld Gmail weekly-manager-task reply slice: one general Gmail + phone
  machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld Gmail scheduled-draft send-now slice: one general Gmail machine
  covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld Gmail read-state calendar-window slice: one general Gmail machine
  covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld Gmail job-search attachment/send slice: one general Gmail +
  file-system machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls,
  and 0 unsafe changes.
- Held-out AppWorld Gmail flight-ticket download slice: one general Gmail + file-system
  machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld Gmail-receipt Venmo payment slice: one general Gmail + file-system +
  Venmo machine covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and
  0 unsafe changes.
- Held-out AppWorld coworker Venmo gift + email slice: one general Venmo + Gmail machine
  covers 3 `test_challenge` tasks with 3/3 success, 0 invalid calls, and 0 unsafe
  changes.
- Held-out AppWorld shared-subscription password + phone-text slice: one general
  Amazon/Spotify + Gmail + phone machine covers 3 `test_challenge` tasks with 3/3
  success, 0 invalid calls, and 0 unsafe changes.
- Development-cost audit: ToolSandbox uses 13 static machines; AppWorld has 116 registered
  machines, with 55 used by the 168 local `test_normal.txt` tasks (3.05 tasks per used
  machine; median used-machine total LOC is 94).

## Key Artifacts

- Paper source and PDF:
  `paper/rave_intent_compiled_verified_execution_arr.tex`,
  `paper/rave_intent_compiled_verified_execution_arr.pdf`
- Artifact manifest:
  `paper/artifact_manifest_rave2.md`
- ToolSandbox primary Qwen2.5-3B runs:
  `results/toolsandbox_qwen25_3b_rave2_single_turn_compare_fixed/20260501_144845/`,
  `results/toolsandbox_qwen25_3b_rave2_insufficient_compare_fixed2/20260501_153424/`
- ToolSandbox guardrail diagnostic:
  `results/toolsandbox_pctu_insufficient_deepseek/20260524_211028/`
- Dynamic boolean-setting induction:
  `results/dynamic_synthesis_probe/20260524_172425/`,
  `results/dynamic_affordance_generalization/20260524_172229/`
- AppWorld targeted 72-task slice:
  `results/appworld_rave_slice_expanded72/20260506_000919/`
- AppWorld local dev57:
  `results/appworld_rave_official_dev57_final/20260506_021705/`,
  `results/appworld_rave_official_dev57_final_llm_intent_deepseek_chat/20260506_021940/`
- AppWorld full local `test_normal.txt` diagnostic:
  `results/appworld_rave_official_test_normal_full168_trip_note_debts_20260524/20260524_225648/`
- AppWorld trip-note debt family check:
  `results/appworld_trip_note_debts_20260524/20260524_225607/`
- AppWorld held-out phone-message account-verification slice:
  `results/appworld_phone_account_verify_reset_20260524/20260524_233807/`
- AppWorld held-out Gmail relation-star slice:
  `results/appworld_gmail_star_relationship_20260524/20260525_000839/`
- AppWorld held-out expired-payment-card cleanup slice:
  `results/appworld_remove_expired_cards_20260525/20260525_002233/`
- AppWorld held-out Venmo password-reset slice:
  `results/appworld_venmo_change_password_20260525/20260525_004717/`
- AppWorld held-out workout-email Spotify playlist slice:
  `results/appworld_spotify_workout_email_playlist_20260525/20260525_005603/`
- AppWorld held-out phone-message Amazon recommendation purchase slice:
  `results/appworld_amazon_phone_recommendation_purchase_20260525/20260525_011413/`
- AppWorld held-out Amazon wishlist itemized-text slice:
  `results/appworld_amazon_wishlist_itemized_text_20260525/20260525_045222/`
- AppWorld held-out Amazon cart+wishlist total answer slice:
  `results/appworld_amazon_cart_wishlist_total_20260525/20260525_045234/`
- AppWorld held-out Amazon wishlist-all order slice:
  `results/appworld_amazon_order_wishlist_all_20260525/20260525_050933/`
- AppWorld held-out Amazon cart+wishlist-all order slice:
  `results/appworld_amazon_order_cart_wishlist_all_20260525/20260525_050918/`
- AppWorld held-out Amazon recent-order return slice:
  `results/appworld_amazon_return_recent_orders_20260525/20260525_052017/`
- AppWorld held-out Amazon last-ordered product question slice:
  `results/appworld_amazon_post_last_order_question_20260525/20260525_052247/`
- AppWorld held-out Amazon last-month review-update slice:
  `results/appworld_amazon_update_last_month_review_20260525/20260525_053844/`
- AppWorld held-out Amazon last-order question-answer slice:
  `results/appworld_amazon_answer_last_order_question_20260525/20260525_055112/`
- AppWorld held-out Amazon verified-purchaser battery-life answer slice:
  `results/appworld_amazon_verified_battery_life_20260525/20260525_060235/`
- AppWorld held-out Gmail-to-Spotify song-recommendation reply slice:
  `results/appworld_spotify_liked_song_email_recommendations_20260525/20260525_013420/`
- AppWorld held-out Spotify draft recommendation update/send slice:
  `results/appworld_spotify_update_song_recommendation_draft_20260525/20260525_014643/`
- AppWorld held-out Venmo optional-signup payment slice:
  `results/appworld_venmo_optional_signup_payment_20260525/20260525_020403/`
- AppWorld held-out Gmail notification-labeling slice:
  `results/appworld_gmail_label_notification_threads_20260525/20260525_021446/`
- AppWorld held-out Gmail priority-relabel slice:
  `results/appworld_gmail_relabel_priority_20260525/20260525_040633/`
- AppWorld held-out Gmail archived-thread calendar-delete slice:
  `results/appworld_gmail_delete_archived_window_20260525/20260525_041422/`
- AppWorld held-out Gmail anniversary-announcement forward slice:
  `results/appworld_gmail_forward_anniversary_announcement_20260525/20260525_042330/`
- AppWorld held-out Gmail caterer-bill manager-forward slice:
  `results/appworld_gmail_forward_caterer_bill_20260525/20260525_043439/`
- AppWorld held-out Gmail weekly-manager-task reply slice:
  `results/appworld_gmail_weekly_manager_tasks_20260525/20260525_044411/`
- AppWorld held-out Gmail scheduled-draft send-now slice:
  `results/appworld_gmail_send_scheduled_now_20260525/20260525_034758/`
- AppWorld held-out Gmail read-state calendar-window slice:
  `results/appworld_gmail_mark_read_state_20260525/20260525_035609/`
- AppWorld held-out Gmail job-search attachment/send slice:
  `results/appworld_gmail_job_search_attach_send_20260525/20260525_023325/`
- AppWorld held-out Gmail flight-ticket download slice:
  `results/appworld_gmail_flight_ticket_download_20260525/20260525_033611/`
- AppWorld held-out Gmail-receipt Venmo payment slice:
  `results/appworld_venmo_flight_bill_email_20260525/20260525_025233/`
- AppWorld held-out coworker Venmo gift + email slice:
  `results/appworld_venmo_coworker_sprint_gifts_20260525/20260525_030821/`
- AppWorld held-out shared-subscription password + phone-text slice:
  `results/appworld_shared_subscription_password_text_20260525/20260525_032327/`
- AppWorld static public-instruction coverage:
  `results/appworld_static_coverage/20260524/`
- Review-strengthening summaries and machine development-cost table:
  `results/icve_review_strengthening/20260524/`

## Reproducing ToolSandbox Runs

Start a local OpenAI-compatible model server, then run the benchmark scripts. For example,
Qwen2.5-3B single-turn:

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/local_openai_transformers_server.py \
  --model Qwen/Qwen2.5-3B-Instruct \
  --host 127.0.0.1 \
  --port 8000 \
  --device cuda

conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/run_toolsandbox_kill_criteria.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-3B-Instruct \
  --methods rave rave_no_rave2_dsl react \
  --scenario-suite single_turn_no_distraction \
  --max-scenarios 0 \
  --output-dir results/reproduce_qwen25_3b_single_turn
```

Qwen2.5-3B insufficient-information:

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/run_toolsandbox_kill_criteria.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-3B-Instruct \
  --methods rave rave_no_abstention react \
  --scenario-suite insufficient_no_distraction \
  --max-scenarios 0 \
  --output-dir results/reproduce_qwen25_3b_insufficient
```

Regenerate summary statistics:

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/summarize_rave2_statistics.py
```

Run the no-LLM dynamic boolean-setting probes:

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/run_dynamic_synthesis_probe.py

conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/run_dynamic_affordance_generalization.py
```

## Reproducing AppWorld Diagnostics

AppWorld experiments require a local AppWorld installation and dataset root. The runners
expect public task instructions and live `apis` access; they do not require ground-truth
answers or compiled solution files.

Targeted AppWorld slice:

```bash
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
PYTHONPATH=<PROJECT_ROOT>/src \
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
python experiments/run_appworld_rave_slice.py \
  --appworld-root appworld_020_root \
  --agent deterministic \
  --experiment-name reproduce_appworld_slice \
  --output-root results/reproduce_appworld_slice
```

Full local `test_normal.txt` diagnostic:

```bash
APPWORLD_ROOT=<PROJECT_ROOT>/appworld_020_root \
PYTHONPATH=<PROJECT_ROOT>/src \
PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
python experiments/run_appworld_rave_slice.py \
  --appworld-root appworld_020_root \
  --agent deterministic \
  --task-ids $(python3 - <<'PY'
from pathlib import Path
ids = []
for line in Path("appworld_020_root/data/datasets/test_normal.txt").read_text().splitlines():
    if line.strip():
        ids.append(line.strip().split(":")[0])
print(" ".join(ids))
PY
) \
  --experiment-name reproduce_appworld_test_normal_full168 \
  --output-root results/reproduce_appworld_test_normal_full168
```

Static public-instruction coverage audit:

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/summarize_appworld_static_coverage.py \
  --output-dir results/appworld_static_coverage/reproduce
```

Review-strengthening analysis:

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/summarize_icve_review_strengthening.py
```

## Main Files

- `src/pctu_pilot/rave_dsl.py`: typed intent frames, schemas, machines, and runtime
  action types.
- `src/pctu_pilot/rave_runtime.py`: benchmark-agnostic registry runtime, state ledger,
  and policy interfaces.
- `src/pctu_pilot/toolsandbox_agents.py`: ToolSandbox ReAct/PCTU/ICVE binding,
  registered machines, and restricted dynamic setting-machine synthesis.
- `src/pctu_pilot/appworld_agents.py`: AppWorld intent machines and real-LLM
  intent/code baselines.
- `experiments/run_toolsandbox_kill_criteria.py`: ToolSandbox runner.
- `experiments/run_appworld_rave_slice.py`: AppWorld deterministic, intent-extraction,
  direct-code, repair, typed-intent-code, and ReAct-code runner.
- `experiments/summarize_appworld_static_coverage.py`: public-instruction compile
  coverage audit.
- `experiments/summarize_icve_review_strengthening.py`: guardrail, coverage-risk, and
  machine-cost summary generator.
- `experiments/build_anonymous_supplement.py`: whitelist-based anonymous supplement
  builder.
- `scripts/scan_for_sensitive_info.py`: repository hygiene scan used before public
  pushes.

## Data and Safety Notes

The repository is intended to contain source code, public task-id lists, paper files, and
summary-level result artifacts. It should not contain real API keys, raw AppWorld
databases, access tokens, downloaded protected bundles, local conda environments, model
caches, or private task logs.

For hosted model replications, use the `.env.example` templates and keep real credentials
outside version control.
