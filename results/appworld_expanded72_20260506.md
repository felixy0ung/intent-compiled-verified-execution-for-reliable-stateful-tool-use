# AppWorld Expanded 72-Task Check, 2026-05-06

This record extends the active AppWorld targeted slice from 66 to 72 public
state-changing tasks by adding two Spotify-only families:

- `d4e9306_*`: follow artists of all liked songs and liked albums.
- `b7a9ee9_*`: follow artists of all genre-specific songs in the user's Spotify
  playlists.

The new machines are:

- `appworld_spotify_follow_artists_from_liked_songs_and_albums`
- `appworld_spotify_follow_playlist_song_artists_by_genre`

The dataset file is `data/datasets/rave_expanded72.txt`.

## Summary Metrics

| row | tasks | success | invalid / task | unsafe / task | LLM calls / task | token proxy / task |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RAVE deterministic runtime | 72 | 72/72 | 0.0694 | 0.0 | 0.0 | 180.5 |
| RAVE + Qwen2.5-3B intent extraction | 72 | 72/72 | 0.0694 | 0.0 | 1.0 | 3220.3 |
| RAVE + DeepSeek-chat intent extraction | 72 | 72/72 | 0.0694 | 0.0 | 1.0 | 3352.2 |
| RAVE + DeepSeek-reasoner intent extraction | 72 | 72/72 | 0.0694 | 0.0 | 1.0 | 3462.3 |
| Qwen2.5-3B direct code | 72 | 0/72 | 1.0000 | 0.0 | 1.0 | 1544.0 |
| Qwen2.5-3B typed-intent then code | 72 | 0/72 | 1.0000 | 0.0 | 2.0 | 4674.8 |
| Qwen2.5-3B code repair | 72 | 0/72 | 2.7083 | 0.0 | 2.8889 | 5342.8 |
| Qwen2.5-3B multi-step code observation | 72 | 0/72 | 3.7500 | 0.0 | 4.3472 | 9031.7 |
| DeepSeek-chat direct code | 72 | 4/72 | 0.8611 | 0.0139 | 1.0 | 2028.9 |
| DeepSeek-chat typed-intent then code | 72 | 7/72 | 0.7917 | 0.0139 | 2.0 | 5478.9 |
| DeepSeek-chat code repair | 72 | 21/72 | 1.5556 | 0.0417 | 2.3472 | 5898.8 |
| DeepSeek-chat multi-step code observation | 72 | 20/72 | 1.2222 | 0.0 | 4.3056 | 12128.6 |

## Packaged Evaluator Reports

AppWorld's packaged evaluator confirms the same task/scenario completion results on
`rave_expanded72`:

| experiment output | task completion | scenario completion |
| --- | ---: | ---: |
| `rave_appworld_expanded72` | 100.0 | 100.0 |
| `rave_appworld_qwen25_3b_intent_expanded72` | 100.0 | 100.0 |
| `rave_appworld_deepseek_chat_intent_combined72` | 100.0 | 100.0 |
| `rave_appworld_deepseek_reasoner_intent_combined72` | 100.0 | 100.0 |
| `appworld_direct_code_qwen25_3b_combined72` | 0.0 | 0.0 |
| `appworld_intent_code_qwen25_3b_combined72` | 0.0 | 0.0 |
| `appworld_code_repair_qwen25_3b_combined72` | 0.0 | 0.0 |
| `appworld_react_code_qwen25_3b_combined72` | 0.0 | 0.0 |
| `appworld_direct_code_deepseek_chat_combined72` | 5.6 | 0.0 |
| `appworld_intent_code_deepseek_chat_combined72` | 9.7 | 4.2 |
| `appworld_code_repair_deepseek_chat_combined72` | 29.2 | 20.8 |
| `appworld_react_code_deepseek_chat_combined72` | 27.8 | 0.0 |

Reports are under:

- `experiments/outputs/rave_appworld_expanded72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/rave_appworld_qwen25_3b_intent_expanded72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/rave_appworld_deepseek_chat_intent_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/rave_appworld_deepseek_reasoner_intent_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_direct_code_qwen25_3b_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_intent_code_qwen25_3b_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_code_repair_qwen25_3b_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_react_code_qwen25_3b_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_direct_code_deepseek_chat_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_intent_code_deepseek_chat_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_code_repair_deepseek_chat_combined72/evaluations/rave_expanded72.{json,txt}`
- `experiments/outputs/appworld_react_code_deepseek_chat_combined72/evaluations/rave_expanded72.{json,txt}`

The DeepSeek-chat and DeepSeek-reasoner intent rows are combined from the preceding
66-task hosted runs plus the final six-task Spotify-family expansion:

- `results/appworld_rave_slice_llm_intent_deepseek_chat_combined72/20260506_003007`
- `results/appworld_rave_slice_llm_intent_deepseek_reasoner_combined72/20260506_003123`

The DeepSeek-chat code baselines are also combined to the same 72-task dataset:

- `results/appworld_llm_direct_code_deepseek_chat_combined72/20260506_003508`
- `results/appworld_llm_intent_code_deepseek_chat_combined72/20260506_003733`
- `results/appworld_llm_code_repair_deepseek_chat_combined72/20260506_003945`
- `results/appworld_llm_react_code_deepseek_chat_combined72/20260506_004300`

## Interpretation

This strengthens the local AppWorld evidence: the same verified runtime now covers 24
registered AppWorld intent machines and 72 public state-changing tasks. The new tasks are
not ground-truth scripted; they are implemented through the typed RAVE runtime and live
AppWorld APIs.

This replaces the earlier mixed local-72 / hosted-66 reporting for the active AppWorld
table. The earlier 66-task hosted rows remain archived in
`results/appworld_rave_slice_20260504.md` and
`results/appworld_official_evaluator_rave_expanded66_20260505.md` for auditability.

The latest official AppWorld 0.2.0 repository-agent runner is tracked separately from
this AppWorld 0.1.x targeted RAVE slice. The constrained DeepSeek
`simplified_react_code_agent` official-runner check reaches 0/10 on `dev10` only under
`max_steps=3`; the more relevant default-50-step `dev10_full50` check reaches 90.0
task-goal / 75.0 scenario-goal completion, while RAVE deterministic and RAVE +
DeepSeek-chat intent extraction both reach 100.0 / 100.0 on the same small official
AppWorld 0.2.0 slice after four additional intent machines are registered. See
`results/appworld_official_runner_dev10_full50_20260506.md`. This is still separate from
the 72-task RAVE table and not full leaderboard coverage.
