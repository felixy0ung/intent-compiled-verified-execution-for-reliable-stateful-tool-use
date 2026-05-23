# ToolSandbox Kill-Criteria Summary

| method | episodes | success_rate | mean_similarity | unsafe_state_changes_per_task | invalid_tool_calls_per_task | verifier_rejections_per_task | repair_calls_per_task | llm_calls_per_task | tool_calls_per_task | token_proxy_per_task | user_llm_calls_per_task | user_token_proxy_per_task | parse_errors_per_task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ToolSandbox RAVE | 5 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| ToolSandbox RAVE - no abstention verifier | 5 | 0.4 | 0.4 | 0.6 | 0.4 | 0.4 | 0.0 | 3.4 | 2.6 | 1710.0 | 0.0 | 0.0 | 0.0 |
| ToolSandbox ReAct | 5 | 0.6 | 0.6 | 0.4 | 0.6 | 0.0 | 0.0 | 4.6 | 3.6 | 2416.6 | 0.0 | 0.0 | 0.0 |
