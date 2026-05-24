#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-conda}"
CONDA_ENV_PATH="${CONDA_ENV_PATH:-pctu-sim}"

: "${FRONTIER_BASE_URL:?Set FRONTIER_BASE_URL, e.g. https://api.openai.com/v1}"
: "${FRONTIER_MODEL:?Set FRONTIER_MODEL, e.g. gpt-4.1-mini}"
: "${FRONTIER_API_KEY:?Set FRONTIER_API_KEY for the endpoint}"

MAX_SCENARIOS="${MAX_SCENARIOS:-0}"
OUTPUT_ROOT="${OUTPUT_ROOT:-results/frontier_toolsandbox_replication}"
SAFE_MODEL="$(printf '%s' "${FRONTIER_MODEL}" | tr '/: ' '___')"

cd "${ROOT_DIR}"

"${CONDA_BIN}" run -p "${CONDA_ENV_PATH}" \
  python experiments/run_toolsandbox_kill_criteria.py \
  --base-url "${FRONTIER_BASE_URL}" \
  --model "${FRONTIER_MODEL}" \
  --methods rave rave_no_rave2_dsl react \
  --scenario-suite single_turn_no_distraction \
  --max-scenarios "${MAX_SCENARIOS}" \
  --output-dir "${OUTPUT_ROOT}/${SAFE_MODEL}_single_turn"

"${CONDA_BIN}" run -p "${CONDA_ENV_PATH}" \
  python experiments/run_toolsandbox_kill_criteria.py \
  --base-url "${FRONTIER_BASE_URL}" \
  --model "${FRONTIER_MODEL}" \
  --methods rave rave_no_abstention react \
  --scenario-suite insufficient_no_distraction \
  --max-scenarios "${MAX_SCENARIOS}" \
  --output-dir "${OUTPUT_ROOT}/${SAFE_MODEL}_insufficient"
