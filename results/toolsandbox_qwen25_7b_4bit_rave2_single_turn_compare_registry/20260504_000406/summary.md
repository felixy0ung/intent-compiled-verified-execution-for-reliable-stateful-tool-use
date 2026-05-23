# ToolSandbox Kill-Criteria Summary

| method | episodes | success_rate | mean_similarity | unsafe_state_changes_per_task | invalid_tool_calls_per_task | verifier_rejections_per_task | repair_calls_per_task | llm_calls_per_task | tool_calls_per_task | token_proxy_per_task | user_llm_calls_per_task | user_token_proxy_per_task | parse_errors_per_task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ToolSandbox RAVE | 30 | 0.9667 | 0.9667 | 0.0 | 0.0 | 0.0 | 1.3333 | 0.5333 | 1.8333 | 249.4 | 0.0 | 0.0 | 0.0 |
| ToolSandbox RAVE - no RAVE-2 DSL | 30 | 0.9 | 0.9267 | 0.0 | 0.0 | 0.1 | 0.8667 | 1.7333 | 2.5 | 1076.8 | 0.0 | 0.0 | 0.0 |
| ToolSandbox ReAct | 30 | 0.1333 | 0.6796 | 0.0 | 0.4 | 0.0 | 0.0 | 5.0333 | 4.2667 | 3358.2667 | 0.0 | 0.0 | 0.0333 |
