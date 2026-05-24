# ICVE Review-Strengthening Analysis

## Guardrail Baseline

On the MiniStore real-LLM diagnostic, PCTU instantiates a stronger ReAct+schema/proof/
verifier guardrail baseline: the model still owns the action loop, but every mutating
action must carry evidence and expected postconditions checked by a runtime verifier.
ReAct has success=0.3750, invalid/tool=1.1250,
unsafe=1.1250. PCTU reduces invalid and unsafe outcomes to
0.0000/0.0000,
but reaches only success=0.2500 with
7.25 LLM calls/task and
3169.4 token proxy/task. ICVE reaches
success=1.0000 with 2.25
LLM calls/task and 603.9 token proxy/task.

On the full 28-scenario DeepSeek-chat ToolSandbox insufficient-information suite, ReAct
reaches success=0.3214 with
unsafe=0.6071 and invalid/tool=1.2143.
PCTU reaches success=0.7500 and
unsafe=0.1786, but still records
invalid/tool=1.0357,
verifier_rejections=2.21,
and 6.79 LLM calls/task. ICVE reaches
success=1.0000 with invalid/tool=0.0000,
unsafe=0.0000, and 0.00
agent LLM calls/task.

## Failure-Mode Shift

On ToolSandbox insufficient-information tasks (`n=28`), ReAct records
success=0.5000, unsafe=0.4286, and
invalid/tool=2.1786. ICVE records
success=1.0000, unsafe=0.0000, and
invalid/tool=0.0000. Removing abstention keeps success at
0.5000 but restores unsafe=0.4286.

## Coverage-Risk Tradeoff

On the local AppWorld `test_normal.txt` diagnostic, ICVE supports 164
of 167 tasks and succeeds on 164 overall
(164 of 164 supported). The remaining
3 tasks are unsupported safe no-action outcomes;
unsafe state changes are 0 and invalid tool calls are
3. The `test_challenge` prefix is a negative-control
diagnostic: after adding two conservative saved-list machines, 12/24 solve, 12/24 remain
unsupported no-action, and unsafe state changes remain 0.

## Machine Coverage and Development Cost

The ToolSandbox binding has 13 static intent machines.
The AppWorld binding has 85 static intent machines; the
full167 diagnostic uses 54 machine types for
164 supported tasks, or
3.04 tasks per used machine. For used AppWorld
machines, median compiler LOC is 18.0, median
handler LOC is 73.5, median total LOC is
93.0, and median slot count is
1.0. Historical adaptation time was not recorded, so the
per-machine table marks `adaptation_time=not_recorded` and uses LOC/coverage as auditable
cost proxies.
