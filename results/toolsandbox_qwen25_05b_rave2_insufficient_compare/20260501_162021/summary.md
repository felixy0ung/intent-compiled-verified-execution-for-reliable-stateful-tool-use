# ToolSandbox Kill-Criteria Summary

| method | episodes | success_rate | mean_similarity | unsafe_state_changes_per_task | invalid_tool_calls_per_task | verifier_rejections_per_task | repair_calls_per_task | llm_calls_per_task | tool_calls_per_task | token_proxy_per_task | user_llm_calls_per_task | user_token_proxy_per_task | parse_errors_per_task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ToolSandbox RAVE | 28 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| ToolSandbox RAVE - no abstention verifier | 28 | 0.6071 | 0.6459 | 0.3214 | 2.3929 | 0.0714 | 0.3214 | 5.1786 | 4.8214 | 5233.6786 | 0.0 | 0.0 | 0.3929 |
| ToolSandbox ReAct | 28 | 0.6071 | 0.6459 | 0.3214 | 3.25 | 0.0 | 0.0 | 8.6429 | 8.0 | 8367.2857 | 0.0 | 0.0 | 0.3929 |
