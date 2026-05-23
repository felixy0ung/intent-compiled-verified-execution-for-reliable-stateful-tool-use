# AppWorld RAVE Slice, 2026-05-04/05

Historical note: this file records the preceding 66-task AppWorld slice. The active
72-task AppWorld result is `results/appworld_expanded72_20260506.md`.

## Setup

- Environment: `<CONDA_ROOT>/envs/pctu-appworld`
- Data root: `<PROJECT_ROOT>/data`
- Runner: `experiments/run_appworld_rave_slice.py`
- Real-LLM intent models: local Qwen2.5-3B through the local OpenAI-compatible CUDA
  server, and DeepSeek `deepseek-chat` / `deepseek-reasoner` through the
  OpenAI-compatible endpoint loaded from `experiments/deepseek_replication.env`
- Task families:
  - `0d8a4ee_*` phone message to non-Venmo contacts
  - `13547f5_*` phone text/voice message to contacts by relationship
  - `37a8675_*` Venmo transfer by phone number
  - `024c982_*` Venmo payment request to a named contact by relationship
  - `4fab96f_*` Venmo reminders for old pending payment requests
  - `6ea6792_*` process pending Venmo payment requests
  - `ff58e36_*` add relationship-matched contacts as Venmo friends if needed
  - `5e27cd7_*` delete Gmail drafts with empty subject/body fields
  - `09ac073_*` archive/delete read Gmail threads while preserving priority/starred exceptions
  - `771d8fc_*` delete spam text/voice messages
  - `cf6abd2_*` Simple Note bucket-list status update
  - `07b42fd_*` Spotify follow artists by genre and follower threshold
  - `aa8502b_*` Spotify follow/unfollow artists by liked-song artists
  - `6171bbc_*` Spotify playlist creation from the best song in each album/playlist
  - `f3f60f0_*` like all unliked songs and albums in Spotify libraries
  - `3ab5b8b_*` download liked songs from Spotify playlist/song/album libraries
  - `692c77d_*` rate liked or unliked Spotify library songs to a target rating
  - `31dc501_*` update weekday/weekend wake-up alarm snooze minutes
  - `07bb666_*` move Amazon cart/wish-list products by rating threshold
  - `396c5a2_*` add Spotify songs by artist and strict play-count threshold to the player queue
  - `57c3486_*` like all songs from artists followed on Spotify
  - `652485c_*` create a public Spotify playlist from liked library songs and share the URL by phone text

## Result

| run | path | episodes | success | unsafe/task | invalid/repair task | API calls/task | LLM calls/task | token proxy/task |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic compiler | `results/appworld_rave_slice_expanded66/20260505_063044` | 66 | 66/66 | 0.0000 | 0.0758 | 26.7121 | 0.0000 | 183.8788 |
| Qwen2.5-3B intent compiler | `results/appworld_rave_slice_llm_intent_qwen25_3b_expanded66/20260505_063133` | 66 | 66/66 | 0.0000 | 0.0758 | 26.7121 | 1.0000 | 3028.2273 |
| DeepSeek-chat intent compiler with slot verifier | `results/appworld_rave_slice_llm_intent_deepseek_chat_expanded66/20260505_063312` | 66 | 66/66 | 0.0000 | 0.0758 | 26.7121 | 1.0000 | 3333.7424 |
| DeepSeek-reasoner intent compiler | `results/appworld_rave_slice_llm_intent_deepseek_reasoner_expanded66/20260505_063509` | 66 | 66/66 | 0.0000 | 0.0758 | 26.7121 | 1.0000 | 3443.8333 |
| Qwen2.5-3B direct-code baseline | `results/appworld_llm_direct_code_qwen25_3b_expanded66/20260505_072403` | 66 | 0/66 | 0.0000 | 1.0000 | 0.4848 | 1.0000 | 1535.2273 |
| Qwen2.5-3B typed-intent-only code ablation | `results/appworld_llm_intent_code_qwen25_3b_expanded66/20260505_073209` | 66 | 0/66 | 0.0000 | 1.0000 | 0.3788 | 2.0000 | 4658.2424 |
| Qwen2.5-3B code-repair baseline | `results/appworld_llm_code_repair_qwen25_3b_expanded66/20260505_075811` | 66 | 0/66 | 0.0000 | 2.7727 | 1.6818 | 2.9242 | 5388.2727 |
| Qwen2.5-3B multi-step code-observation baseline | `results/appworld_llm_react_code_qwen25_3b_expanded66/20260505_074139` | 66 | 0/66 | 0.0000 | 3.8182 | 1.6364 | 4.4697 | 9243.7576 |
| DeepSeek direct-code baseline | `results/appworld_llm_direct_code_expanded66/20260505_063829` | 66 | 4/66 | 0.0152 | 0.8788 | 22.8939 | 1.0000 | 2024.3939 |
| DeepSeek typed-intent-only code ablation | `results/appworld_llm_intent_code_expanded66/20260505_064515` | 66 | 7/66 | 0.0152 | 0.7727 | 103.4697 | 2.0000 | 5460.4697 |
| DeepSeek code-repair baseline | `results/appworld_llm_code_repair_deepseek_chat_combined66/20260505_143100` | 66 | 19/66 | 0.0455 | 1.5606 | 37.4697 | 2.3485 | 5916.9697 |
| DeepSeek multi-step code-observation baseline | `results/appworld_llm_react_code_deepseek_chat_combined66/20260505_143100` | 66 | 18/66 | 0.0000 | 1.1667 | 21.9848 | 4.2576 | 11869.1818 |

The DeepSeek smoke run also passed on three cross-family tasks:
`results/appworld_rave_slice_llm_intent_smoke/20260504_135808`.
The wake-up alarm snooze extension smoke run passed 3/3:
`results/appworld_rave_slice_phone_alarm_snooze_smoke/20260505_021334`.

The direct-code baseline was also smoke-tested at
`results/appworld_llm_direct_code_smoke/20260504_141547`; the full recorded baseline with
model metadata is `results/appworld_llm_direct_code_full/20260504_141829`.
The code-repair baseline was smoke-tested at
`results/appworld_llm_code_repair_smoke/20260504_145518`; the full recorded baseline with
model metadata is `results/appworld_llm_code_repair_full/20260504_145658`.
The earlier smaller slice remains recorded under the `*_full`, `expanded39`,
`expanded45`, `expanded48`, `expanded51`, `expanded54`, `expanded57`, `expanded60`, and
`expanded63` paths. The expanded 66-task typed-runtime runs above were the pre-72
headline AppWorld slice. The local Qwen2.5-3B code-repair and multi-step
code-observation baselines are full 66-task runs. DeepSeek code-repair and multi-step
code-observation were also reported as combined 66-task hosted baselines assembled
from incrementally flushed shards. The preceding 63-task hosted baselines remain under
`results/appworld_llm_code_repair_expanded63/20260505_055055` and
`results/appworld_llm_react_code_expanded63/20260505_060421` as historical references
only and are not the active AppWorld comparison rows.

The same then-active 66-task outputs were re-evaluated with AppWorld's packaged evaluator
using `data/datasets/rave_expanded66.txt`. The official evaluator reports are summarized
in `results/appworld_official_evaluator_rave_expanded66_20260505.md`. They confirm
100.0 task/scenario completion for the deterministic and real-LLM RAVE runtime rows,
0.0 for the three local Qwen code baselines, 6.1 task completion for DeepSeek direct
code, 28.8 task completion for hosted DeepSeek code repair, and 27.3 task completion for
hosted DeepSeek multi-step code-observation.

The new cross-app playlist-sharing family (`652485c_*`) was also smoke-tested with local
Qwen2.5-3B baselines to isolate repair cost on the newest tasks:

| run | path | episodes | success | unsafe/task | invalid/repair task | LLM calls/task | token proxy/task |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic compiler | `results/appworld_rave_slice_share_playlist_smoke/20260505_063030` | 3 | 3/3 | 0.0000 | 0.0000 | 0.0000 | 237.0 |
| Qwen2.5-3B direct-code baseline | `results/appworld_llm_direct_code_qwen_share_playlist_smoke/20260505_071918` | 3 | 0/3 | 0.0000 | 1.0000 | 1.0000 | 1798.0 |
| Qwen2.5-3B typed-intent-only code ablation | `results/appworld_llm_intent_code_qwen_share_playlist_smoke/20260505_071948` | 3 | 0/3 | 0.0000 | 1.0000 | 2.0000 | 4768.7 |
| Qwen2.5-3B multi-step code-observation baseline | `results/appworld_llm_react_code_qwen_share_playlist_smoke/20260505_072016` | 3 | 0/3 | 0.0000 | 2.0000 | 2.0000 | 3810.0 |
| Qwen2.5-3B code-repair baseline | `results/appworld_llm_code_repair_qwen_share_playlist_smoke/20260505_072057` | 3 | 0/3 | 0.0000 | 3.0000 | 3.0000 | 7023.0 |
| DeepSeek-reasoner direct-code baseline | `results/appworld_llm_direct_code_deepseek_reasoner_share_playlist_smoke/20260505_082154` | 3 | 0/3 | 0.0000 | 1.0000 | 1.0000 | 2521.0 |
| DeepSeek-reasoner typed-intent-only code ablation | `results/appworld_llm_intent_code_deepseek_reasoner_share_playlist_smoke/20260505_082245` | 3 | 0/3 | 0.0000 | 1.0000 | 2.0000 | 6027.3 |
| DeepSeek-chat code-repair baseline | `results/appworld_llm_code_repair_deepseek_chat_share_playlist_smoke/20260505_082511` | 3 | 0/3 | 0.0000 | 2.0000 | 3.0000 | 11297.7 |
| DeepSeek-chat multi-step code-observation baseline | `results/appworld_llm_react_code_deepseek_chat_share_playlist_smoke/20260505_082721` | 3 | 1/3 | 0.0000 | 0.0000 | 5.0000 | 15855.7 |

The DeepSeek-reasoner direct-code smoke produced invalid unsupported outputs on this
family rather than valid AppWorld state transitions. A 66-task DeepSeek-reasoner
direct-code attempt was not reported because the hosted API stalled on the first episode
before producing any metrics; the empty result directory was removed.

DeepSeek-chat repair and multi-step observation are mixed on the same family: repair stays
at 0/3 while increasing invalid/repair attempts to 2.0 per task and token proxy to
11297.7 per task; multi-step observation reaches 1/3 with no invalid calls, but uses 5.0
LLM calls and 15855.7 token proxy per task. This is a useful sanity check that the
baseline can sometimes make progress, but it still trails the verified runtime's 3/3.

After adding incremental flushing/resume support to the runner, we also ran DeepSeek-chat
hosted repair/ReAct on a six-task slice covering `57c3486_*` and `652485c_*`:

| run | path | episodes | success | unsafe/task | invalid/repair task | LLM calls/task | token proxy/task |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepSeek-chat code-repair six-task slice | `results/appworld_llm_code_repair_deepseek_chat_incremental6/20260505_083339` | 6 | 3/6 | 0.0000 | 2.0000 | 3.0000 | 9177.3 |
| DeepSeek-chat multi-step code-observation six-task slice | `results/appworld_llm_react_code_deepseek_chat_incremental6/20260505_083153` | 6 | 3/6 | 0.0000 | 0.8333 | 4.3333 | 13141.0 |

These hosted baselines solve the easier followed-artist song-liking family in several
cases but still miss the cross-app playlist-sharing tasks. They are useful diagnostics,
not replacements for a full AppWorld leaderboard-style comparison.

The same incremental runner was then used on a twelve-task hosted DeepSeek-chat slice
covering Amazon rating-filtered cart/wish-list moves, Spotify artist queue additions,
followed-artist song liking, and cross-app playlist sharing:

| run | path | episodes | success | unsafe/task | invalid/repair task | LLM calls/task | token proxy/task |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepSeek-chat code-repair twelve-task slice | `results/appworld_llm_code_repair_deepseek_chat_incremental12/20260505_083849` | 12 | 6/12 | 0.0000 | 1.7500 | 2.6667 | 7213.3 |
| DeepSeek-chat multi-step code-observation twelve-task slice | `results/appworld_llm_react_code_deepseek_chat_incremental12/20260505_084238` | 12 | 5/12 | 0.0000 | 0.7500 | 4.1667 | 11947.5 |

This larger hosted slice again shows partial baseline competence, but also persistent
failure and high model cost on several stateful families that the verified runtime solves
deterministically.

## Interpretation

This is a real public stateful benchmark slice on AppWorld, but it is intentionally
small and has been superseded by the 72-task active slice. The expanded 66-task slice spans twenty-two public state-changing task families. The local
Qwen2.5-3B and hosted DeepSeek runs use a real LLM only for typed intent/slot extraction;
the state-changing execution is still performed by RAVE's verified AppWorld runtime.
Qwen2.5-3B, verified `deepseek-chat`, and `deepseek-reasoner` preserve 66/66 success on this
slice.

The unverified DeepSeek-chat intent run
`results/appworld_rave_slice_llm_intent_expanded60/20260505_041527` is intentionally
kept as an AppWorld slot-verifier ablation: it reached 59/60 with 0.0167 unsafe
state-test failures per task after extracting `archive` for a task whose instruction
began with `Delete`. The instruction-aware slot verifier repairs that high-risk action
slot before execution and restores 60/60 with zero unsafe changes.

This result strengthens the second-benchmark evidence from "deterministic compiler
transfer" to "real-LLM intent extraction plus verified runtime transfer." It is still not
a full AppWorld leaderboard run or broad AppWorld controller.

The latest official AppWorld repository-agent runner was also tested in
`results/appworld_official_agent_attempt_20260505.md`. Its package stack imports in an
isolated environment, but task execution is blocked by missing Git LFS app/test bundles,
so this historical report does not claim official repository-agent or leaderboard-agent
coverage. The Git LFS blocker was later resolved. The constrained `max_steps=3` `dev10`
smoke remains in `results/appworld_official_runner_dev10_20260506.md`; the stronger
default-50-step follow-up is `results/appworld_official_runner_dev10_full50_20260506.md`,
where official DeepSeek ReAct-code reaches 90.0 task-goal / 75.0 scenario-goal
completion and RAVE reaches 100.0 / 100.0 on the same small AppWorld 0.2.0 slice.

The direct-code baseline is intentionally simple: the model receives the task instruction
and a compact API sketch, then writes one AppWorld code cell. It is not an official
AppWorld leaderboard agent, but it is a useful sanity baseline for this slice. Qwen2.5-3B
direct code reaches 0/66; DeepSeek-chat direct code reaches 4/66. These failures mostly
come from brittle API/data-shape assumptions such as expecting
`relationship` or `id` fields in returned records, mishandling search result shapes, or
failing before the required state mutation. This contrast supports the paper's claim that
the typed runtime owns more than schema validation: it encodes grounded evidence lookup
and state-transition logic.

The typed-intent-only code ablation controls for the intent parser: DeepSeek first
extracts a typed intent frame, but then writes the AppWorld code itself instead of
using the verified RAVE handler. DeepSeek reaches only 7/66 on this historical slice; local
Qwen2.5-3B reaches 0/66. This suggests that the verified state-machine runtime, not just
typed intent recognition, is carrying the AppWorld result.

The local Qwen2.5-3B code-repair and multi-step code-observation baselines also reach
0/66 on this historical slice. Code-repair uses 2.9242 LLM calls and 5388.3 token proxy per
task while increasing invalid/repair attempts to 2.7727 per task. Multi-step
code-observation uses 4.4697 LLM calls and 9243.8 token proxy per task while increasing
invalid/repair attempts to 3.8182 per task. Repair and observation do not recover the
weak model's code-generation failures.

The DeepSeek repair baseline is stronger than direct code but still trails the verified runtime: it can use
execution feedback to patch broken code, which improves success on spam-delete,
Gmail draft deletion, Spotify-follow, and some phone/Venmo tasks, but it still reaches
only 19/66 and suffers from brittle assumptions, much higher repair/token cost, and
unsafe state changes on the Gmail thread cleanup family.

The multi-step code-observation baseline is closer to a ReAct-style AppWorld controller:
it can inspect live state and issue multiple code cells. It improves over direct-code but
still reaches only 18/66 success, with substantially higher LLM/token cost than the
verified runtime.

The Venmo transfer family incurs RAVE repair cost because AppWorld hides payment-card
balances, so the runtime must probe non-expired cards until one succeeds.
