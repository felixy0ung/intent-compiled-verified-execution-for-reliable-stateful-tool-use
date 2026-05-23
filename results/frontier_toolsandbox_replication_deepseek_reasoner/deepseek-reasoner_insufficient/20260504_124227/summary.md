# ToolSandbox Kill-Criteria Summary

| method | episodes | success_rate | mean_similarity | unsafe_state_changes_per_task | invalid_tool_calls_per_task | verifier_rejections_per_task | repair_calls_per_task | llm_calls_per_task | tool_calls_per_task | token_proxy_per_task | user_llm_calls_per_task | user_token_proxy_per_task | parse_errors_per_task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ToolSandbox RAVE | 28 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| ToolSandbox RAVE - no abstention verifier | 28 | 0.8929 | 0.9364 | 0.0 | 0.0714 | 0.0 | 0.25 | 0.8929 | 0.1786 | 649.1429 | 0.0 | 0.0 | 0.0714 |
| ToolSandbox ReAct | 28 | 0.9286 | 0.9721 | 0.0 | 0.0357 | 0.0 | 0.0 | 1.1071 | 0.1071 | 753.4643 | 0.0 | 0.0 | 0.0714 |
