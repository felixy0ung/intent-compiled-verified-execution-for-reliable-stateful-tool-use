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
  `test_normal.txt` instructions and 30/417 local `test_challenge.txt` instructions.
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
- Development-cost audit: ToolSandbox uses 13 static machines; AppWorld has 90 registered
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
