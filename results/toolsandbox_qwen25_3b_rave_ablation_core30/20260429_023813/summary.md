# ToolSandbox Kill-Criteria Summary

| method | episodes | success_rate | mean_similarity | unsafe_state_changes_per_task | invalid_tool_calls_per_task | verifier_rejections_per_task | repair_calls_per_task | llm_calls_per_task | tool_calls_per_task | token_proxy_per_task | user_llm_calls_per_task | user_token_proxy_per_task | parse_errors_per_task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ToolSandbox RAVE | 30 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0333 | 1.7 | 0.2667 | 1.9333 | 69.8333 | 0.0 | 0.0 | 0.0 |
| ToolSandbox RAVE - no argument normalizer | 30 | 0.9667 | 0.9667 | 0.0 | 0.0 | 0.0333 | 1.7 | 0.7333 | 2.4 | 336.2667 | 0.0 | 0.0 | 0.0 |
| ToolSandbox RAVE - no completion detector | 30 | 0.0333 | 0.718 | 0.0 | 1.2333 | 0.0333 | 1.7 | 9.1667 | 10.3333 | 9600.3333 | 0.0 | 0.0 | 0.3667 |
| ToolSandbox RAVE - no intent compiler | 30 | 0.5333 | 0.6354 | 0.0 | 0.3 | 0.1 | 0.0667 | 3.8667 | 3.6333 | 2270.3 | 0.0 | 0.0 | 0.3 |
| ToolSandbox RAVE - no precondition repair | 30 | 0.7333 | 0.7664 | 0.0 | 0.8667 | 0.2667 | 2.0333 | 2.1 | 3.8667 | 937.4 | 0.0 | 0.0 | 0.0 |
| ToolSandbox ReAct | 30 | 0.0 | 0.3258 | 0.0 | 1.9 | 0.0 | 0.0 | 8.2 | 7.3667 | 6547.6667 | 0.0 | 0.0 | 0.3 |
