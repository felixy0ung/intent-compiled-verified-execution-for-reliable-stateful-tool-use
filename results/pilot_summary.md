# Pilot Summary

| method | episodes | task_success_rate | goal_achieved_rate | invalid_tool_calls_per_task | unsafe_changes_per_task | collateral_changes_per_task | verifier_rejections_per_task | recovery_after_rejection_rate | llm_calls_per_task | tool_calls_per_task | token_proxy_per_task |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Proof-Carrying Tool Use | 500 | 0.996 | 0.996 | 0.0 | 0.0 | 0.0 | 2.124 | 0.996 | 5.118 | 2.994 | 1301.48 |
| ReAct | 500 | 0.472 | 0.742 | 0.57 | 0.436 | 0.144 | 0.0 |  | 2.156 | 2.156 | 732.14 |
| ReAct + JSON repair | 500 | 0.468 | 0.794 | 0.566 | 0.496 | 0.146 | 0.0 |  | 2.124 | 2.124 | 718.53 |
| ReAct + retry | 500 | 0.538 | 0.848 | 0.628 | 0.454 | 0.136 | 0.0 |  | 2.724 | 2.724 | 1020.81 |
| ReAct + state ledger | 500 | 0.688 | 0.91 | 0.352 | 0.262 | 0.02 | 0.0 |  | 2.616 | 2.616 | 550.12 |
| Risk-Adaptive Verified Execution | 500 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.354 | 1.0 | 1.0 | 3.0 | 180.0 |
