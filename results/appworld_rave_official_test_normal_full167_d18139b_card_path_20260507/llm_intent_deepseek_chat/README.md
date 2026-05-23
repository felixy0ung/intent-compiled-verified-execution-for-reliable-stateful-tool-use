# AppWorld test_normal full local file summary

Agent: llm_intent_deepseek_chat

This combines the first-120 run and the 121--167 continuation over the local `appworld_020_root/data/datasets/test_normal.txt` file. It is still a local AppWorld 0.2.0 file-level run, not a public leaderboard submission.

| metric | value |
| --- | --- |
| method | rave_appworld_llm_intent_slice |
| episodes | 167 |
| success_rate | 0.982 |
| supported_rate | 0.982 |
| invalid_tool_calls_per_task | 0.018 |
| unsafe_state_changes_per_task | 0.0 |
| api_calls_per_task | 38.4132 |
| code_exec_calls_per_task | 0.982 |
| llm_calls_per_task | 1.0 |
| prompt_tokens_per_task | 11341.8263 |
| completion_tokens_per_task | 34.6108 |
| token_proxy_per_task | 11376.4371 |

## Counts

- success: 164/167
- supported: 164/167
- supported success: 164/164
- invalid tool calls: 3
- unsafe state changes: 0

## Failures

- 3b8fb7a_1: unsupported, supported=0, invalid=1
- 3b8fb7a_2: unsupported, supported=0, invalid=1
- 3b8fb7a_3: unsupported, supported=0, invalid=1
