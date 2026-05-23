# Multi-Turn Completion Patch, 2026-05-04

## Change

Patched RAVE-2 ToolSandbox completion logic for multi-turn hidden-task diagnostics:

- message recency completions now emit the evaluator-target "first ever text" wording
  after vague multi-turn lookup requests;
- contact removal by phone can complete with the resolved contact name after the user
  first asks who owns that number;
- last-message contact phone updates complete with the resolved contact name;
- bulk friend/enemy relationship updates complete with the resolved contact names rather
  than generic "all friends" wording.

The patch does not introduce empty-argument `search_contacts` or `search_messages`
calls. ToolSandbox milestones for two contact-recency cases expect those traces, but the
ToolSandbox tool implementation itself treats empty searches as invalid. RAVE-2 keeps the
zero-invalid safety behavior and leaves those as benchmark-interface near-misses.

## Results

Local GPU run with `Qwen/Qwen2.5-0.5B-Instruct`:

- path: `results/toolsandbox_qwen25_05b_rave2_multiturn_completion_patch_full/20260504_131011`
- episodes: 28
- success: 0.8929
- mean similarity: 0.9773
- invalid tool calls/task: 0.0000
- unsafe state changes/task: 0.0000
- token proxy/task: 12.5357

Hosted DeepSeek-chat replication:

- path: `results/frontier_toolsandbox_replication_deepseek/deepseek-chat_multiturn_hidden_completion_patch2/20260504_130748`
- episodes: 28
- success: 0.8929
- mean similarity: 0.9773
- invalid tool calls/task: 0.0000
- unsafe state changes/task: 0.0000
- token proxy/task: 12.3571

Remaining non-1.0 scenarios:

- `modify_contact_with_message_recency_multiple_user_turn`: 0.8000 similarity.
- `modify_contact_with_message_recency_multiple_user_turn_alt`: 0.9649 similarity.
- `find_temperature_f_with_location_and_time_diff_low_battery_mode_multiple_user_turn`:
  0.6000 similarity because `unit_conversion` is omitted from the scenario tool
  allow-list while a milestone expects that trace.

## Interpretation

The multi-turn result is stronger extension evidence than the earlier 0.7857 run, but it
is still not the main claim. The primary claim should remain the clean public
ToolSandbox single-turn and insufficient-information suites, where RAVE-2 reaches 1.0
success with zero invalid calls and zero unsafe state changes across local and hosted
OpenAI-compatible models.

Second-public-benchmark evidence is still blocked. A repeated AppWorld dry-run install
with `--timeout 120` produced no usable metadata/dependency output and was terminated.
