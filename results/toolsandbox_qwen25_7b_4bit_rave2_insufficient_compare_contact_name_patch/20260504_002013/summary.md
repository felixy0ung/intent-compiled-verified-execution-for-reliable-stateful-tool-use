# ToolSandbox Kill-Criteria Summary

| method | episodes | success_rate | mean_similarity | unsafe_state_changes_per_task | invalid_tool_calls_per_task | verifier_rejections_per_task | repair_calls_per_task | llm_calls_per_task | tool_calls_per_task | token_proxy_per_task | user_llm_calls_per_task | user_token_proxy_per_task | parse_errors_per_task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ToolSandbox RAVE | 28 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.5714 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| ToolSandbox RAVE - no abstention verifier | 28 | 0.5357 | 0.5665 | 0.3929 | 0.5714 | 0.5714 | 0.3929 | 4.3214 | 3.1429 | 2624.25 | 0.0 | 0.0 | 0.3214 |
| ToolSandbox ReAct | 28 | 0.4286 | 0.449 | 0.3929 | 1.2143 | 0.0 | 0.0 | 7.1071 | 5.0714 | 4894.3571 | 0.0 | 0.0 | 0.3571 |
