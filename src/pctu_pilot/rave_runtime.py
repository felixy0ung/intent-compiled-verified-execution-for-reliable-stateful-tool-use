from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from .rave_dsl import FinalAction, IntentFrame, IntentMachine, RuntimeAction, ToolAction


AvailableTools = dict[str, Callable[..., Any]]
InsufficientInfoVerifier = Callable[[str, AvailableTools], Optional[IntentFrame]]
AbstentionMessageBuilder = Callable[[IntentFrame], str]


class RaveStateLedger(Protocol):
    """Benchmark-facing state evidence interface used by RAVE bindings.

    Concrete benchmarks decide how to parse observations and what state objects they
    track. The runtime-facing contract is intentionally small: ingest user/tool evidence,
    expose groundedness checks, and answer whether a tool transition has already
    succeeded or failed.
    """

    def record_user_message(self, content: str) -> None: ...

    def observe(self, tool: str, args: dict[str, Any], content: str, error: Optional[str]) -> None: ...

    def is_value_grounded(self, value: Any) -> bool: ...

    def to_prompt_json(self) -> str: ...

    def last_successful_observation(self) -> Optional[dict[str, Any]]: ...

    def has_successful_observation(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> bool: ...

    def has_failed_observation(
        self,
        tool: str,
        args_subset: Optional[dict[str, Any]] = None,
    ) -> bool: ...


@dataclass(frozen=True)
class RaveRuntimeResult:
    frame: Optional[IntentFrame]
    action: Optional[ToolAction | FinalAction]


CompletionDetector = Callable[[str, str, AvailableTools], Optional[FinalAction]]
ActionVerifier = Callable[[IntentFrame, RuntimeAction, AvailableTools], RuntimeAction]


class RaveRuntimePolicy(Protocol):
    """Policy adapter supplied by a benchmark binding.

    RAVE's generic runtime owns compile/dispatch. A domain policy owns final-message
    wording and domain-specific rejection of candidate runtime actions.
    """

    def abstention_message(self, frame: IntentFrame) -> str: ...

    def verify_action(
        self,
        frame: IntentFrame,
        action: RuntimeAction,
        available_tools: AvailableTools,
    ) -> RuntimeAction: ...


@dataclass(frozen=True)
class RaveRuntimeHooks:
    completion_detector: Optional[CompletionDetector] = None
    abstention_message: Optional[AbstentionMessageBuilder] = None
    action_verifier: Optional[ActionVerifier] = None

    @classmethod
    def from_policy(
        cls,
        policy: RaveRuntimePolicy,
        *,
        completion_detector: Optional[CompletionDetector] = None,
        enable_abstention: bool = True,
    ) -> "RaveRuntimeHooks":
        return cls(
            completion_detector=completion_detector,
            abstention_message=policy.abstention_message if enable_abstention else None,
            action_verifier=policy.verify_action,
        )


class RaveRuntime:
    """Benchmark-agnostic ICVE registry runtime.

    Domain bindings provide intent machines and an optional insufficient-information
    verifier. The runtime owns the generic compile/dispatch loop: run the verifier, try
    registered compilers in order, validate frames against schemas, and dispatch the frame
    to the handler registered for its intent type.
    """

    def __init__(
        self,
        intent_machines: list[IntentMachine],
        insufficient_info_verifier: Optional[InsufficientInfoVerifier] = None,
    ) -> None:
        self.intent_machines = list(intent_machines)
        self.intent_machine_by_type = {
            machine.schema.intent_type: machine for machine in self.intent_machines
        }
        if len(self.intent_machine_by_type) != len(self.intent_machines):
            raise ValueError("IntentMachine intent_type values must be unique.")
        self.insufficient_info_verifier = insufficient_info_verifier

    def compile_frame(
        self,
        request: str,
        raw_request: str,
        available_tools: AvailableTools,
    ) -> Optional[IntentFrame]:
        if not request:
            return None

        if self.insufficient_info_verifier is not None:
            insufficient = self.insufficient_info_verifier(request, available_tools)
            if insufficient is not None:
                return insufficient

        for machine in self.intent_machines:
            frame = machine.compiler(request, raw_request, available_tools)
            if frame is None:
                continue
            frame.validate(machine.schema)
            return frame
        return None

    def next_frame_action(
        self,
        frame: IntentFrame,
        available_tools: AvailableTools,
    ) -> Optional[ToolAction]:
        machine = self.intent_machine_by_type.get(frame.intent_type)
        if machine is None:
            return None
        return machine.handler(frame, available_tools)

    def step(
        self,
        request: str,
        raw_request: str,
        available_tools: AvailableTools,
        *,
        hooks: Optional[RaveRuntimeHooks] = None,
    ) -> RaveRuntimeResult:
        hooks = hooks or RaveRuntimeHooks()
        if hooks.completion_detector is not None:
            final = hooks.completion_detector(request, raw_request, available_tools)
            if final is not None:
                return RaveRuntimeResult(frame=None, action=final)

        frame = self.compile_frame(request, raw_request, available_tools)
        if frame is None:
            return RaveRuntimeResult(frame=None, action=None)
        if frame.abstain_reason and hooks.abstention_message is not None:
            return RaveRuntimeResult(
                frame=frame,
                action=FinalAction(
                    message=hooks.abstention_message(frame),
                    reason=f"abstain_{frame.intent_type}:{frame.abstain_reason}",
                ),
            )
        action = self.next_frame_action(frame, available_tools)
        if action is not None and hooks.action_verifier is not None:
            action = hooks.action_verifier(frame, action, available_tools)
        return RaveRuntimeResult(frame=frame, action=action)
