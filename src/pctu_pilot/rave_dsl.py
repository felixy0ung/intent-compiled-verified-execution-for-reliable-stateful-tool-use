from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class RaveRuntimeOptions:
    enable_intent_compiler: bool = True
    enable_argument_normalizer: bool = True
    enable_precondition_repair: bool = True
    enable_completion_detector: bool = True
    enable_rave2_dsl: bool = True
    enable_abstention_verifier: bool = True
    enable_dynamic_machine_synthesis: bool = False
    use_static_intent_machines: bool = True


@dataclass(frozen=True)
class SlotSpec:
    name: str
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class IntentSchema:
    intent_type: str
    slots: tuple[SlotSpec, ...] = ()
    terminal_states: tuple[str, ...] = ("done", "abstain")

    @property
    def required_slots(self) -> tuple[str, ...]:
        return tuple(slot.name for slot in self.slots if slot.required)


@dataclass
class IntentSlot:
    name: str
    value: Any = None
    required: bool = True
    source: str = ""

    @property
    def filled(self) -> bool:
        return self.value is not None


@dataclass
class IntentFrame:
    """Typed intent frame used by ICVE compilers.

    A frame is the runtime-owned state for a user intent: typed slots, state-machine
    state, missing information, and abstention status. Domain compilers fill slots;
    state-machine handlers consume frames and emit verified actions.
    """

    intent_type: str
    slots: dict[str, IntentSlot] = field(default_factory=dict)
    state: str = "ready"
    missing_slots: list[str] = field(default_factory=list)
    abstain_reason: str = ""

    def set_slot(self, name: str, value: Any, *, source: str = "", required: bool = True) -> None:
        self.slots[name] = IntentSlot(name=name, value=value, required=required, source=source)

    def get(self, name: str, default: Any = None) -> Any:
        slot = self.slots.get(name)
        if slot is None or slot.value is None:
            return default
        return slot.value

    def require(self, *names: str) -> None:
        self.missing_slots = [
            name
            for name in names
            if name not in self.slots or self.slots[name].value is None
        ]

    def validate(self, schema: IntentSchema) -> None:
        self.require(*schema.required_slots)

    @property
    def complete(self) -> bool:
        return not self.missing_slots and not self.abstain_reason


@dataclass(frozen=True)
class ToolAction:
    tool: str
    args: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class FinalAction:
    message: str
    reason: str


RuntimeAction = ToolAction | FinalAction
IntentCompiler = Callable[[str, str, dict[str, Callable[..., Any]]], Optional[IntentFrame]]
StateMachineHandler = Callable[[IntentFrame, dict[str, Callable[..., Any]]], Optional[ToolAction]]


@dataclass(frozen=True)
class IntentMachine:
    schema: IntentSchema
    compiler: IntentCompiler
    handler: StateMachineHandler
