# Dynamic Affordance-Generalization Diagnostic - 2026-05-24

## Proposal

The extension is a conservative affordance-template induction path for ICVE. Instead of
claiming open-ended machine synthesis, the runtime discovers a narrow class of stateful
tool affordances from API names and signatures:

- getter: `get_<setting>_status() -> bool`
- setter: `set_<setting>_status(on: bool) -> None`

For an unsupported request that uniquely mentions a discovered setting and an
enable/disable/status operation, the runtime proposes a typed `IntentMachine`, executes
it in shadow mode, checks that the candidate only emits whitelisted getter/setter tools,
checks the setter signature, and rejects candidates that match unrelated counterexample
requests.

## Reasonableness Review

This is a plausible generalization claim because the induced unit is not tied to a
manually registered task family such as Wi-Fi or cellular service. The machine is derived
from an API affordance pattern and can handle previously unseen setting names.

The claim remains intentionally bounded. It does not synthesize AppWorld purchase,
vacation-settlement, payment, search, or multi-entity workflows. Those require entity
grounding, joins, authorization, and richer postconditions that cannot be inferred safely
from a boolean setter signature alone.

## Experiment Design

Script:

```bash
conda run -p <CONDA_ROOT>/envs/pctu-sim \
  python experiments/run_dynamic_affordance_generalization.py
```

Configuration:

- Static registry disabled.
- LLM client stubbed; any LLM call raises an error.
- Five held-out regular boolean-setting API pairs are provided:
  `bluetooth`, `dark_mode`, `privacy_mode`, `roaming_data`, and `auto_sync`.
- Two negative cases are provided:
  an invalid `focus_mode` setter whose parameter is named `enabled` rather than `on`,
  and an unrelated stock-symbol request.

Output:

- `results/dynamic_affordance_generalization/20260524_172229/episode_metrics.csv`
- `results/dynamic_affordance_generalization/20260524_172229/summary.json`

## Result Review

The diagnostic records 7/7 expected outcomes:

- 5/5 held-out boolean-setting requests induced machines and emitted the expected setter
  actions.
- 5/5 induced actions were executed against the synthetic state store.
- Final state mutations were verified:
  `bluetooth=True`, `dark_mode=False`, `privacy_mode=True`, `roaming_data=True`,
  and `auto_sync=False`.
- 2/2 negative cases were rejected.
- LLM calls: 0.
- Promoted machines: 5.

Interpretation for the paper: this strengthens the open-coverage story from
"hand-register every supported task family" to "ICVE can safely induce checked machines
for a signature-identifiable affordance family." It should be described as bounded
affordance-level generalization, not as general automatic state-machine synthesis.
